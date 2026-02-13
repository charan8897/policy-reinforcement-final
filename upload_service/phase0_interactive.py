"""
Phase 0: Interactive Conversation Engine
CompliAssure - Policy Assistant with Gemini LLM

Manages conversation flow:
1. Welcome user & get name
2. Ask about policy document
3. Wait for upload or generate
4. Track pipeline status
"""

import google.generativeai as genai
import json
from datetime import datetime
import logging

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyAgWfY5zft6IV00Y2HwPc3JHQva38zWEDQ"
GEMINI_MODEL = "gemma-3-27b-it"

genai.configure(api_key=GEMINI_API_KEY)

# Setup logging
logger = logging.getLogger(__name__)


class Phase0ConversationManager:
    """
    Manages Phase 0 interactive conversation with user
    """
    
    def __init__(self):
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        self.conversation_state = {}
        self.conversation_history = []
        
    def initialize_session(self, session_id):
        """Initialize a new conversation session"""
        self.conversation_state = {
            'session_id': session_id,
            'stage': 'greeting',  # greeting -> name -> document_check -> waiting -> processing
            'user_name': None,
            'has_document': None,
            'document_id': None,
            'created_at': datetime.now().isoformat(),
            'conversation_turn': 0
        }
        self.conversation_history = []
        
        return self.get_greeting_message()
    
    def get_greeting_message(self):
        """Initial greeting message"""
        message = (
            "🛡️ Welcome to CompliAssure!\n\n"
            "I'm your AI-powered Policy Compliance Assistant. "
            "I'll help you analyze, understand, and enforce your policies.\n\n"
            "May I know your name?"
        )
        
        self.conversation_history.append({
            'sender': 'bot',
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        
        self.conversation_state['stage'] = 'greeting'
        
        return {
            'response': message,
            'stage': 'greeting',
            'action': 'await_input'
        }
    
    def process_user_input(self, user_message, session_id):
        """Process user input and determine next action"""
        
        self.conversation_history.append({
            'sender': 'user',
            'message': user_message,
            'timestamp': datetime.now().isoformat()
        })
        
        current_stage = self.conversation_state.get('stage', 'greeting')
        
        # Stage 1: Get user name
        if current_stage == 'greeting':
            return self.handle_name_input(user_message)
        
        # Stage 2: Ask about document
        elif current_stage == 'name_received':
            return self.handle_document_question(user_message)
        
        # Stage 3: Wait for document upload
        elif current_stage == 'waiting_for_document':
            return self.handle_upload_check(user_message)
        
        # Stage 4: During processing
        elif current_stage == 'processing':
            return self.handle_processing_stage(user_message)
        
        # Default: Continue conversation
        else:
            return self.handle_general_chat(user_message)
    
    def handle_name_input(self, user_message):
        """Extract name from user input"""
        
        # Use LLM to extract name intelligently
        extraction_prompt = f"""
Extract the user's name from this message. If no name is provided, respond with "no_name".
If they refuse or say they prefer not to share, respond with "prefer_not_to_say".

User message: "{user_message}"

Respond with ONLY the extracted name or the codes above.
"""
        
        try:
            response = self.model.generate_content(extraction_prompt)
            extracted_name = response.text.strip()
            
            if extracted_name.lower() == 'no_name':
                self.conversation_state['user_name'] = 'Friend'
                bot_response = (
                    "No worries! I'll call you 'Friend' then 😊\n\n"
                    "Now, do you already have a policy document that you'd like me to analyze? "
                    "Or would you like me to help you generate one?"
                )
                
                # Generate options for document choice
                doc_options = self.generate_dynamic_options(
                    "User wants to know whether to upload existing policy or generate new one. Give clear options.",
                    num_options=2
                )
            elif extracted_name.lower() == 'prefer_not_to_say':
                self.conversation_state['user_name'] = 'User'
                bot_response = (
                    "Understood! No problem at all.\n\n"
                    "Now, do you already have a policy document that you'd like me to analyze? "
                    "Or would you like me to help you generate one?"
                )
                
                # Generate options for document choice
                doc_options = self.generate_dynamic_options(
                    "User wants to know whether to upload existing policy or generate new one. Give clear options.",
                    num_options=2
                )
            else:
                self.conversation_state['user_name'] = extracted_name
                bot_response = (
                    f"Nice to meet you, {extracted_name}! 👋\n\n"
                    f"Do you already have a policy document that you'd like me to analyze? "
                    f"Or would you like me to help you generate one?"
                )
            
            self.conversation_history.append({
                'sender': 'bot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            self.conversation_state['stage'] = 'name_received'
            
            # Generate options for document choice (upload vs generate)
            doc_options = self.generate_dynamic_options(
                "User wants to choose between uploading an existing policy document OR generating a new one. Create 2 clear, distinct options with emoji prefixes.",
                num_options=2
            )
            
            return {
                'response': bot_response,
                'stage': 'name_received',
                'user_name': self.conversation_state['user_name'],
                'action': 'show_options',
                'options': doc_options
            }
        
        except Exception as e:
            logger.error(f"Error extracting name: {e}")
            return {
                'response': "Sorry, I didn't catch that. Could you please tell me your name?",
                'stage': 'greeting',
                'action': 'await_input',
                'error': str(e)
            }
    
    def generate_dynamic_options(self, context, num_options=3):
        """Use LLM to generate contextual options"""
        
        options_prompt = f"""Generate {num_options} clickable options ONLY as JSON array. Return NOTHING else.

Context: {context}

RETURN ONLY THIS FORMAT:
[
  {{"label": "📋 Option 1", "value": "option_1", "description": "Description for option 1"}},
  {{"label": "📊 Option 2", "value": "option_2", "description": "Description for option 2"}},
  {{"label": "🔐 Option 3", "value": "option_3", "description": "Description for option 3"}}
]
"""
        
        try:
            response = self.model.generate_content(options_prompt)
            response_text = response.text.strip()
            
            logger.info(f"[OPTIONS] Raw response: {response_text[:200]}")
            
            # Remove markdown if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Find JSON array in response
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']') + 1
            if start_idx >= 0 and end_idx > start_idx:
                response_text = response_text[start_idx:end_idx]
            
            logger.info(f"[OPTIONS] Extracted JSON: {response_text[:200]}")
            
            options = json.loads(response_text)
            if isinstance(options, list) and len(options) > 0:
                logger.info(f"[OPTIONS] Successfully generated {len(options)} options")
                return options
            
            logger.warning(f"[OPTIONS] Invalid options format: {options}")
            return None
        
        except json.JSONDecodeError as e:
            logger.error(f"[OPTIONS] JSON decode error: {e} | Response: {response_text[:200]}")
            return None
        except Exception as e:
            logger.error(f"[OPTIONS] Error generating options: {e}")
            return None
    
    def handle_document_question(self, user_message):
        """Determine if user has document or needs generation"""
        
        check_prompt = f"""
Does the user want to UPLOAD an existing policy document or GENERATE a new one?
Respond with ONLY one word: "upload" or "generate"

User message: "{user_message}"
"""
        
        try:
            response = self.model.generate_content(check_prompt)
            choice = response.text.strip().lower()
            
            if 'upload' in choice:
                self.conversation_state['has_document'] = True
                self.conversation_state['stage'] = 'waiting_for_document'
                
                # Generate dynamic response using LLM
                upload_prompt = f"""
You are CompliAssure, a friendly policy assistant.
The user wants to upload an existing policy document.

Generate a brief, welcoming response (1-2 sentences) that:
1. Acknowledges their choice
2. Asks them to upload the document
3. Briefly mentions what you'll do once uploaded

Keep it warm and conversational.
"""
                
                try:
                    llm_response = self.model.generate_content(upload_prompt)
                    bot_response = llm_response.text.strip()
                except Exception as e:
                    logger.error(f"Error generating upload response: {e}")
                    bot_response = "Great! Please upload your policy document and I'll analyze it for you."
                
                action = 'wait_for_upload'
                options = None
            
            elif 'generate' in choice:
                self.conversation_state['has_document'] = False
                self.conversation_state['stage'] = 'waiting_for_details'
                
                bot_response = (
                    f"Understood! I can help you generate a policy document.\n\n"
                    f"What type of policy would you like to create?"
                )
                
                # Generate options dynamically
                options = self.generate_dynamic_options(
                    "User wants to generate a new policy. Suggest common policy types organizations use.",
                    num_options=4
                )
                
                action = 'show_options' if options else 'await_input'
            
            else:
                bot_response = (
                    f"I'm not sure if you want to upload or generate a policy. "
                    f"Could you clarify your preference?"
                )
                
                # Generate options dynamically
                options = self.generate_dynamic_options(
                    "User is unsure about uploading vs generating a policy. Suggest both options clearly.",
                    num_options=2
                )
                
                action = 'show_options' if options else 'await_input'
            
            self.conversation_history.append({
                'sender': 'bot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'response': bot_response,
                'stage': self.conversation_state['stage'],
                'has_document': self.conversation_state['has_document'],
                'action': action,
                'options': options
            }
        
        except Exception as e:
            logger.error(f"Error in document question: {e}")
            return {
                'response': "Let me clarify: Would you like to upload an existing policy or generate a new one?",
                'stage': 'name_received',
                'action': 'await_input',
                'error': str(e)
            }
    
    def handle_upload_check(self, user_message):
        """Check if user is uploading or asking about the process"""
        
        # User is likely asking about the upload process or confirming
        response_prompt = f"""
You are CompliAssure, a friendly policy assistant.
The user has chosen to upload a policy document.

User's message: "{user_message}"

Generate a brief, conversational response that:
1. Acknowledges what they said
2. Reminds them to upload using the 📎 Attach button
3. Offers to help once document is uploaded

Keep it varied - avoid repeating the same phrasing.
Response should be 1-2 short sentences max.
"""
        
        try:
            response = self.model.generate_content(response_prompt)
            bot_response = response.text.strip()
            
            self.conversation_history.append({
                'sender': 'bot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'response': bot_response,
                'stage': 'waiting_for_document',
                'action': 'wait_for_upload'
            }
        
        except Exception as e:
            logger.error(f"Error in upload check: {e}")
            return {
                'response': "I'm ready to analyze your document whenever you upload it!",
                'stage': 'waiting_for_document',
                'action': 'wait_for_upload',
                'error': str(e)
            }
    
    def handle_document_uploaded(self, document_id, filename):
        """Handle document upload notification"""
        
        self.conversation_state['document_id'] = document_id
        self.conversation_state['stage'] = 'processing'
        
        bot_response = (
            f"✅ Document received: {filename}\n\n"
            f"🔄 Your document is being processed through our 10-stage pipeline:\n"
            f"• Stage 1: Clause Extraction\n"
            f"• Stage 2: Intent Classification\n"
            f"• Stage 3: Entity Extraction\n"
            f"• Stage 4: Ambiguity Detection\n"
            f"• Stage 5-10: Clarification & Rule Generation\n\n"
            f"I'll keep you updated on the progress..."
        )
        
        self.conversation_history.append({
            'sender': 'bot',
            'message': bot_response,
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            'response': bot_response,
            'stage': 'processing',
            'document_id': document_id,
            'action': 'show_progress_modal',
            'modal_message': (
                "Your document is being processed...\n\n"
                "We will send you a notification when complete.\n\n"
                "Progress: [████░░░░░░] 40%"
            )
        }
    
    def handle_processing_stage(self, user_message):
        """Handle messages during processing"""
        
        response_prompt = f"""
The user's document is being processed. 
Generate a reassuring response and remind them you'll notify when done.

User message: "{user_message}"

Keep it brief and calming.
"""
        
        try:
            response = self.model.generate_content(response_prompt)
            bot_response = response.text.strip()
            
            self.conversation_history.append({
                'sender': 'bot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'response': bot_response,
                'stage': 'processing',
                'action': 'continue_processing'
            }
        
        except Exception as e:
            logger.error(f"Error in processing stage: {e}")
            return {
                'response': "Your document is still being processed. I'll notify you as soon as it's ready!",
                'stage': 'processing',
                'action': 'continue_processing',
                'error': str(e)
            }
    
    def handle_general_chat(self, user_message):
        """Handle general conversation"""
        
        context = (
            f"You are CompliAssure, a helpful policy analysis assistant.\n"
            f"User Name: {self.conversation_state.get('user_name', 'User')}\n"
            f"Current Stage: {self.conversation_state.get('stage', 'unknown')}\n\n"
            f"Respond helpfully to the user's message."
        )
        
        chat_prompt = f"{context}\n\nUser: {user_message}"
        
        try:
            response = self.model.generate_content(chat_prompt)
            bot_response = response.text.strip()
            
            self.conversation_history.append({
                'sender': 'bot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'response': bot_response,
                'stage': self.conversation_state.get('stage'),
                'action': 'await_input'
            }
        
        except Exception as e:
            logger.error(f"Error in general chat: {e}")
            return {
                'response': "I'm here to help with your policy analysis. How can I assist?",
                'stage': self.conversation_state.get('stage'),
                'action': 'await_input',
                'error': str(e)
            }
    
    def get_conversation_history(self):
        """Get full conversation history"""
        return {
            'session_id': self.conversation_state.get('session_id'),
            'state': self.conversation_state,
            'history': self.conversation_history
        }


# Global session manager
_sessions = {}


def get_or_create_session(session_id):
    """Get or create a conversation session"""
    if session_id not in _sessions:
        _sessions[session_id] = Phase0ConversationManager()
        _sessions[session_id].initialize_session(session_id)
    return _sessions[session_id]


def process_chat_message(session_id, user_message):
    """Process a chat message for a session"""
    session = get_or_create_session(session_id)
    return session.process_user_input(user_message, session_id)


def handle_document_upload(session_id, document_id, filename):
    """Notify session about document upload"""
    session = get_or_create_session(session_id)
    return session.handle_document_uploaded(document_id, filename)
