#!/usr/bin/env python
"""
Token Manager Testing Tool

This script tests the TokenManager's token counting and limit checking functions.
It helps verify whether token calculations are accurate and limits are enforced correctly.
"""

import os
import sys
import asyncio
import json
import logging
import django
from datetime import datetime
import uuid

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.agents.chat.managers.token_manager import TokenManager
from apps.agents.models import Conversation, TokenUsage, ChatMessage, User
from django.db import transaction
from typing import Dict, List, Any
from asgiref.sync import sync_to_async  # Import sync_to_async

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Message:
    """Simple message class to mimic chat messages for token counting tests"""
    def __init__(self, content, role="user"):
        self.content = content
        self.role = role

class TokenManagerTester:
    """Tests TokenManager functionality for accuracy"""

    def __init__(self):
        self.user = None  # Initialize as None, will be set in setup

    @sync_to_async
    def _get_or_create_test_user(self):
        """Get or create a test user for our tests (sync operation)"""
        try:
            return User.objects.get(username="token_test_user")
        except User.DoesNotExist:
            return User.objects.create_user(
                username="token_test_user",
                email="token_test@example.com",
                password="password123"
            )

    @sync_to_async
    def _create_test_conversation(self):
        """Set up a test conversation and return its ID (sync operation)"""
        conversation_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
        with transaction.atomic():
            conversation = Conversation.objects.create(
                session_id=session_id,
                user=self.user,
                title="Token Manager Test"
            )
            
            # Create some test messages with known token counts
            messages = [
                "This is a short test message.",
                "This is a slightly longer message that should have more tokens than the first one.",
                "This is an even longer message that discusses various topics in depth to ensure we have a substantial token count for our tests. It includes multiple sentences and tries to be verbose enough to get a decent token count.",
            ]
            
            for i, content in enumerate(messages):
                ChatMessage.objects.create(
                    conversation=conversation,
                    session_id=session_id,
                    user=self.user,
                    content=content,
                    is_agent=(i % 2 == 1)  # Alternate between user and agent
                )
                
            # Create some TokenUsage records manually with known values
            token_counts = [
                {"prompt": 10, "completion": 20, "total": 30},
                {"prompt": 25, "completion": 35, "total": 60},
                {"prompt": 40, "completion": 50, "total": 90},
            ]
            
            for i, counts in enumerate(token_counts):
                TokenUsage.objects.create(
                    conversation=conversation,
                    prompt_tokens=counts["prompt"],
                    completion_tokens=counts["completion"],
                    total_tokens=counts["total"],
                    model="gpt-3.5-turbo",
                    metadata={"test_index": i}
                )
                
        return conversation.session_id

    @sync_to_async
    def _get_direct_token_usage(self, conversation_id):
        """Get token usage directly from the database (sync operation)"""
        try:
            conversation = Conversation.objects.get(session_id=conversation_id)
            actual_usage = TokenUsage.objects.filter(conversation=conversation).values_list(
                'prompt_tokens', 'completion_tokens', 'total_tokens'
            )
            
            prompt_sum = sum(u[0] for u in actual_usage)
            completion_sum = sum(u[1] for u in actual_usage)
            total_sum = sum(u[2] for u in actual_usage)
            
            return {
                "prompt_tokens": prompt_sum,
                "completion_tokens": completion_sum,
                "total_tokens": total_sum
            }
        except Exception as e:
            logger.error(f"Error in direct token usage query: {str(e)}")
            return {"error": str(e)}

    async def setup_test_conversation(self) -> str:
        """Set up a test conversation and return its ID"""
        # First ensure we have a user
        if self.user is None:
            self.user = await self._get_or_create_test_user()
        
        # Then create the conversation
        return await self._create_test_conversation()

    def test_count_tokens(self) -> Dict[str, int]:
        """Test the TokenManager's count_tokens function with various text inputs"""
        tm = TokenManager(model_name="gpt-3.5-turbo")
        
        test_texts = [
            "",  # Empty string
            "Hello, world!",  # Short text
            "This is a longer text with multiple sentences. It should have more tokens than the previous examples. We want to make sure the token counting is accurate for various lengths of text.",  # Medium text
            "A" * 1000,  # Repeating character
            """This is a multi-line text.
            It has line breaks and various forms of whitespace.
            Let's see how it counts tokens in this case.""",  # Multi-line
            json.dumps({"key": "value", "nested": {"inner": "content"}}),  # JSON string
        ]
        
        results = {}
        for i, text in enumerate(test_texts):
            token_count = tm.count_tokens(text)
            results[f"text_{i}"] = {
                "text": text[:50] + "..." if len(text) > 50 else text,
                "tokens": token_count
            }
            logger.info(f"Text {i}: {token_count} tokens")
            
        return results

    async def test_conversation_token_usage(self, conversation_id: str) -> Dict[str, int]:
        """Test the get_conversation_token_usage function"""
        tm = TokenManager(conversation_id=conversation_id)
        
        # First, get the actual values we inserted using sync_to_async
        logger.info("Querying actual TokenUsage records directly...")
        actual_usage = await self._get_direct_token_usage(conversation_id)
        
        if "error" in actual_usage:
            return actual_usage
            
        logger.info(f"Direct DB query - Prompt: {actual_usage['prompt_tokens']}, " +
                    f"Completion: {actual_usage['completion_tokens']}, Total: {actual_usage['total_tokens']}")
        
        # Now test the TokenManager function
        logger.info("Testing TokenManager.get_conversation_token_usage()...")
        try:
            tm_usage = await tm.get_conversation_token_usage()
            logger.info(f"TokenManager result: {tm_usage}")
            
            # Check if values match
            is_accurate = (
                tm_usage['prompt_tokens'] == actual_usage['prompt_tokens'] and
                tm_usage['completion_tokens'] == actual_usage['completion_tokens'] and
                tm_usage['total_tokens'] == actual_usage['total_tokens']
            )
            
            if is_accurate:
                logger.info("✅ get_conversation_token_usage is accurate")
            else:
                logger.error("❌ get_conversation_token_usage is NOT accurate")
                logger.error(f"Expected: {actual_usage}")
                logger.error(f"Got: {tm_usage}")
                
            return {
                "expected": actual_usage,
                "actual": tm_usage,
                "is_accurate": is_accurate
            }
        except Exception as e:
            logger.error(f"Error in get_conversation_token_usage: {str(e)}")
            return {"error": str(e)}

    async def test_check_token_limit(self, conversation_id: str) -> Dict[str, Any]:
        """Test the check_token_limit function with various message sets"""
        tm = TokenManager(
            conversation_id=conversation_id,
            max_token_limit=200  # Small limit for testing
        )
        
        # Create test messages with known token counts (approximated)
        test_message_sets = [
            # Small set (should be under limit)
            [Message("Hello there!")],
            
            # Medium set (might be under limit)
            [
                Message("This is a test message."),
                Message("This is a response to your test message.", "assistant")
            ],
            
            # Large set (should exceed limit)
            [
                Message("This is a very long message that contains many tokens. " * 10),
                Message("This is another very long response that also contains many tokens. " * 10, "assistant")
            ]
        ]
        
        results = {}
        
        for i, messages in enumerate(test_message_sets):
            # Count tokens in this message set
            set_tokens = sum(tm.count_tokens(m.content) for m in messages)
            
            # Get current conversation usage
            conv_usage = await tm.get_conversation_token_usage()
            conv_total = conv_usage['total_tokens']
            
            # Predicted result based on our calculation
            predicted_total = conv_total + set_tokens
            predicted_result = predicted_total <= tm.max_token_limit
            
            # Test the check_token_limit function
            try:
                actual_result = await tm.check_token_limit(messages)
                
                results[f"set_{i}"] = {
                    "messages_token_count": set_tokens,
                    "conversation_tokens": conv_total,
                    "predicted_total": predicted_total,
                    "max_limit": tm.max_token_limit,
                    "predicted_result": predicted_result,
                    "actual_result": actual_result,
                    "is_consistent": predicted_result == actual_result
                }
                
                if predicted_result == actual_result:
                    logger.info(f"✅ Set {i}: check_token_limit is consistent (returned {actual_result})")
                else:
                    logger.error(f"❌ Set {i}: check_token_limit is NOT consistent")
                    logger.error(f"Expected: {predicted_result}, Got: {actual_result}")
                    logger.error(f"Message tokens: {set_tokens}, Conv tokens: {conv_total}, Total: {predicted_total}, Limit: {tm.max_token_limit}")
            except Exception as e:
                logger.error(f"Error testing set {i}: {str(e)}")
                results[f"set_{i}"] = {"error": str(e)}
                
        return results

    async def run_all_tests(self):
        """Run all token manager tests"""
        logger.info("=== Starting TokenManager Tests ===")
        
        # Test basic token counting
        logger.info("\n\n=== Testing count_tokens ===")
        token_count_results = self.test_count_tokens()
        
        # Create test conversation and test token usage/limits
        logger.info("\n\n=== Setting up test conversation ===")
        conversation_id = await self.setup_test_conversation()
        
        logger.info("\n\n=== Testing get_conversation_token_usage ===")
        usage_results = await self.test_conversation_token_usage(conversation_id)
        
        logger.info("\n\n=== Testing check_token_limit ===")
        limit_results = await self.test_check_token_limit(conversation_id)
        
        # Return all results
        return {
            "count_tokens": token_count_results,
            "conversation_token_usage": usage_results,
            "check_token_limit": limit_results
        }

async def main():
    """Main function to run the tests"""
    tester = TokenManagerTester()
    results = await tester.run_all_tests()
    
    # Print summary
    print("\n\n=== TEST SUMMARY ===")
    
    # Token counting summary
    print("\nToken Counting Test:")
    for text_id, data in results["count_tokens"].items():
        print(f"- {text_id}: {data['tokens']} tokens")
    
    # Conversation usage summary
    print("\nConversation Token Usage Test:")
    usage = results["conversation_token_usage"]
    if "error" in usage:
        print(f"❌ Error: {usage['error']}")
    else:
        accuracy = "✅ ACCURATE" if usage.get("is_accurate") else "❌ INACCURATE"
        print(f"{accuracy}")
        print(f"Expected: {usage['expected']}")
        print(f"Actual: {usage['actual']}")
    
    # Token limit summary
    print("\nCheck Token Limit Test:")
    for set_id, data in results["check_token_limit"].items():
        if "error" in data:
            print(f"- {set_id}: ❌ Error: {data['error']}")
        else:
            consistency = "✅ CONSISTENT" if data["is_consistent"] else "❌ INCONSISTENT"
            print(f"- {set_id}: {consistency}")
            print(f"  Message tokens: {data['messages_token_count']}")
            print(f"  Conversation tokens: {data['conversation_tokens']}")
            print(f"  Total: {data['predicted_total']} / Limit: {data['max_limit']}")
            print(f"  Expected result: {data['predicted_result']}, Actual result: {data['actual_result']}")

if __name__ == "__main__":
    asyncio.run(main())