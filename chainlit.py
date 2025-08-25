

import chainlit as cl
from app import call_agent, get_user_from_db, get_department_from_db, create_session, save_to_memory_userdetails

@cl.password_auth_callback
def password_auth_callback(username: str, password: str):
    """
    username -> email
    password -> name
    """
    user = get_user_from_db(username, password)
    if not user:
        return None
    
    # Get department info
    department = get_department_from_db(username)
    
    # Create session and save user details
    session_id = create_session()
    save_to_memory_userdetails(session_id, "user", user["name"], department["department"])
    
    # Return user object with session_id in metadata
    # DO NOT use cl.user_session here - context not available yet
    return cl.User(
        identifier=user["email_id"],
        metadata={
            "name": user["name"], 
            "id": user["position_number"], 
            "department": department["department"], 
            "session_id": session_id
        }
    )   

@cl.on_chat_start
async def start():
    # Now we can access user session and set session_id
    user = cl.user_session.get("user")
    if user and user.metadata.get("session_id"):
        cl.user_session.set("session_id", user.metadata["session_id"])
    
    await cl.Message(
        content="👋 Hi I am your **Finance Chatbot**. You can ask me about finance."
    ).send()
 
@cl.on_message
async def main(message: cl.Message):
    user_input = message.content
    
    # Get session_id from user session
    session_id = cl.user_session.get("session_id")
    
    # If session_id is not in user_session, try to get it from user metadata
    if not session_id:
        user = cl.user_session.get("user")
        if user and user.metadata.get("session_id"):
            session_id = user.metadata["session_id"]
            cl.user_session.set("session_id", session_id)
    
    # print(f"Session ID: {session_id}")
    
    try:
        # Call SQL Agent
        response = call_agent(user_input, session_id)
 
        # Make sure response is string before sending
        if response is None:
            response = "⚠️ No response returned from SQL Agent."
        else:
            response = str(response)
 
        await cl.Message(content=response).send()
 
    except Exception as e:
        await cl.Message(content=f"⚠️ Error: {str(e)}").send()