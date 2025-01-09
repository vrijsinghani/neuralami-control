from http import HTTPStatus
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from PIL import Image
import io
from django.http import HttpResponse
import os

from apps.api.serializers import *
from apps.agents.tools.google_analytics_tool.generic_google_analytics_tool import GenericGoogleAnalyticsTool
import logging

logger = logging.getLogger(__name__)

class BaseToolView(APIView):
    """Base view for tool endpoints"""
    # permission_classes = (IsAuthenticated,)
    # authentication_classes = [TokenAuthentication, SessionAuthentication]
    tool_class = None
    serializer_class = None
    
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(data={
                **serializer.errors,
                'success': False
            }, status=HTTPStatus.BAD_REQUEST)
            
        try:
            # Initialize the tool
            tool = self.tool_class()
            
            # Execute the tool with validated data
            result = tool._run(**serializer.validated_data)
            
            return Response(data={
                'data': result,
                'success': True
            }, status=HTTPStatus.OK)
            
        except Exception as e:
            return Response(data={
                'message': str(e),
                'success': False
            }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

class GoogleAnalyticsToolView(BaseToolView):
    tool_class = GenericGoogleAnalyticsTool
    serializer_class = GoogleAnalyticsToolSerializer

class ImageConversionView(APIView):
    SUPPORTED_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'}
    MAX_DIMENSION = 3840  # 4K resolution max
    serializer_class = ImageConversionSerializer
    
    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            if not serializer.is_valid():
                return Response(data={
                    **serializer.errors,
                    'success': False
                }, status=HTTPStatus.BAD_REQUEST)
            
            # Get the uploaded image
            image_file = serializer.validated_data['image']
            quality = serializer.validated_data['quality']
            max_width = serializer.validated_data.get('max_width')
            max_height = serializer.validated_data.get('max_height')
            
            # Get original filename and size
            original_name = os.path.splitext(image_file.name)[0]
            original_size = image_file.size / 1024  # Convert to KB
            
            # Open image and get format
            img = Image.open(image_file)
            input_format = img.format.upper()
            logger.info(f"Input image: format={input_format}, mode={img.mode}, size={img.size}")
            
            # Check if format is supported
            if input_format not in self.SUPPORTED_FORMATS:
                return Response(data={
                    'message': f'Unsupported image format: {input_format}',
                    'success': False
                }, status=HTTPStatus.BAD_REQUEST)
            
            # Handle alpha channel and color mode conversion
            if img.mode in ('RGBA', 'LA'):
                logger.info("Converting image with alpha channel")
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img, mask=img.split()[1])
                img = background
            elif img.mode != 'RGB':
                logger.info(f"Converting {img.mode} image to RGB")
                img = img.convert('RGB')
            
            # Handle resizing
            if max_width or max_height or img.size[0] > self.MAX_DIMENSION or img.size[1] > self.MAX_DIMENSION:
                orig_width, orig_height = img.size
                target_width = min(max_width or self.MAX_DIMENSION, self.MAX_DIMENSION)
                target_height = min(max_height or self.MAX_DIMENSION, self.MAX_DIMENSION)
                
                ratio = min(target_width/orig_width, target_height/orig_height)
                
                if ratio < 1:
                    new_size = (int(orig_width * ratio), int(orig_height * ratio))
                    logger.info(f"Resizing image from {img.size} to {new_size}")
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to WebP
            webp_buffer = io.BytesIO()
            img.save(
                webp_buffer,
                format='WEBP',
                quality=quality,
                method=6,  # Maximum compression
                lossless=False,  # Use lossy compression for better file size
                exact=False  # Allow WebP encoder to optimize
            )
            
            webp_buffer.seek(0)
            webp_content = webp_buffer.getvalue()
            new_size = len(webp_content) / 1024  # Convert to KB
            
            # Calculate size reduction
            size_reduction = ((original_size - new_size) / original_size) * 100
            
            logger.info(
                f"WebP conversion successful - Original: {original_size:.1f}K, "
                f"New: {new_size:.1f}K, "
                f"Reduction: {size_reduction:.1f}%"
            )
            
            response = HttpResponse(
                webp_content,
                content_type='image/webp'
            )
            response['Content-Disposition'] = f'attachment; filename="{original_name}.webp"'
            return response
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}", exc_info=True)
            return Response(data={
                'message': str(e),
                'success': False
            }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
