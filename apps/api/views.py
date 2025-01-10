from http import HTTPStatus
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.parsers import MultiPartParser
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

class ImageOptimizeUserThrottle(UserRateThrottle):
    rate = '100/day'

    def allow_request(self, request, view):
        if request.user.is_authenticated:
            # Exempt staff and superusers from rate limiting
            if request.user.is_staff or request.user.is_superuser:
                return True
            
            # Exempt users with specific permissions
            if request.user.has_perm('api.unlimited_image_optimize'):
                return True
                
            # Exempt specific users by username or other criteria
            if request.user.username in ['premium_user1', 'premium_user2']:
                return True
                
        # For all other users, apply normal rate limiting
        return super().allow_request(request, view)

class ImageOptimizeAnonThrottle(AnonRateThrottle):
    rate = '10/day'

class ImageOptimizeView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ImageOptimizeUserThrottle, ImageOptimizeAnonThrottle]
    parser_classes = [MultiPartParser]
    
    SUPPORTED_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'}
    MAX_DIMENSION = 3840  # 4K resolution max
    serializer_class = ImageConversionSerializer
    
    def process_image(self, image_file, quality, max_width=None, max_height=None):
        """Process a single image file and return optimized WebP response"""
        try:
            # Get original filename and size
            original_name = os.path.splitext(image_file.name)[0]
            original_size = image_file.size / 1024  # Convert to KB
            
            # Open image and get format
            img = Image.open(image_file)
            input_format = img.format  # Store format before any operations
            logger.info(f"Initial image: format={input_format}, mode={img.mode}, size={img.size}")
            
            # Add EXIF orientation handling
            try:
                exif = img._getexif()
                if exif:
                    orientation = exif.get(274)  # 274 is the orientation tag
                    if orientation:
                        # Rotate or flip the image according to EXIF orientation
                        rotate_values = {
                            3: Image.Transpose.ROTATE_180,
                            6: Image.Transpose.ROTATE_270,
                            8: Image.Transpose.ROTATE_90
                        }
                        if orientation in rotate_values:
                            img = img.transpose(rotate_values[orientation])
                            img.format = input_format  # Restore the format after rotation
                            logger.info(f"Applied EXIF rotation: {orientation}")
            except (AttributeError, KeyError, IndexError):
                logger.debug("No EXIF data found or unable to process EXIF")
                pass

            if not input_format:
                input_format = 'JPEG'  # Default to JPEG if format is unknown
                logger.warning(f"No format detected, defaulting to {input_format}")
                
            input_format = input_format.upper()
            logger.info(f"Processing image: format={input_format}, mode={img.mode}, size={img.size}")
            
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
    
    def post(self, request):
        try:
            logger.info(f"ImageOptimizeView received request: data={request.data}, FILES={request.FILES}")
            serializer = self.serializer_class(data=request.data)
            if not serializer.is_valid():
                logger.error(f"Serializer validation failed: {serializer.errors}")
                return Response(data={
                    **serializer.errors,
                    'success': False
                }, status=HTTPStatus.BAD_REQUEST)
            
            # Log the user making the request
            logger.info(f"Processing request for user: {request.user.username}")
            
            return self.process_image(
                serializer.validated_data['image'],
                serializer.validated_data['quality'],
                serializer.validated_data.get('max_width'),
                serializer.validated_data.get('max_height')
            )
            
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return Response(data={
                'message': str(e),
                'success': False
            }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
