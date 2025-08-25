
import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import text, create_engine
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
                                                                
# ---------------------------
# Setup
# ---------------------------
load_dotenv(dotenv_path=".env")

# Main DB (finance data)
db = SQLDatabase.from_uri("sqlite:///finance.db")

# Engines
memory_engine = create_engine("sqlite:///memory.db")
table_engine = create_engine("sqlite:///finance.db")

# Create memory table if not exists
with memory_engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS conversation_memory_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            user TEXT,
            department TEXT,
            message TEXT
        )
    """))

# Create memory table if not exists
with memory_engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS memory_user_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            user TEXT,
            department TEXT
        )
    """))

# LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0
)

# Global session tracker
session_id = None

# ---------------------------
# User Authentication
# ---------------------------
def get_user_from_db(email: str, name: str):
    """Fetch user from employee table by email + name."""
    with table_engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT position_number, name, email_id
                FROM employee
                WHERE email_id = :email AND name = :name
            """),
            {"email": email.strip(), "name": name.strip()}
        ).fetchone()

    if result:
        return dict(result._mapping)  # return as dict
    return None

def get_user_details_from_db(session_id: str):
    with memory_engine.begin() as conn:
        result = conn.execute(
            text("""SELECT user, department
                    FROM memory_user_details
                    WHERE session_id = :session_id
                 """),
            {"session_id": session_id}
        )
        row = result.fetchone()
        if row:
            return {"username": row.user, "department": row.department}
        return None
    
def get_department_from_db(email: str):
    with table_engine.begin() as conn:
        result = conn.execute(
            text("""SELECT department
                    FROM payroll_budget
                    WHERE email_id = :email
                 """),
            {"email": email}
        )
        row = result.fetchone()
        if row:
            return dict(row._mapping)  # {"department":...}
        return None

# ---------------------------
# Memory Helpers
# ---------------------------
def create_session() -> str:
    return str(uuid.uuid4())

def save_to_memory_userdetails(session_id: str, role: str, user: str, department: str):
    with memory_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO memory_user_details (session_id, role, user, department)
                VALUES (:session_id, :role, :user, :department)
            """),
            {"session_id": session_id, "role": role, "user": user, "department": department}
        )

def save_to_memory(session_id: str, role: str, message: str):
    """Save conversation to memory with user and department info"""
    # Get user details for this session
    user_details = get_user_details_from_db(session_id)
    user = user_details["username"] if user_details else "Unknown"
    department = user_details["department"] if user_details else "Unknown"
    
    with memory_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO conversation_memory_user (session_id, role, user, department, message)
                VALUES (:session_id, :role, :user, :department, :message)
            """),
            {"session_id": session_id, "role": role, "user": user, "department": department, "message": message}
        )


def load_from_memory(session_id: str):
    """Load conversation history for a session"""
    with memory_engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT role, message 
                FROM conversation_memory_user 
                WHERE session_id = :session_id 
                ORDER BY id
            """),
            {"session_id": session_id}
        ).fetchall()

    return [{"role": row[0], "content": row[1]} for row in result]


# ---------------------------
# Agent Logic
# ---------------------------
def call_agent(user_query: str, session_id: str) -> str:
    """Main entry: process user query with SQL Agent + memory."""
    username = "Unknown"
    department = "Unknown"
    
    if not session_id:
        session_id = create_session()
    else:
        details = get_user_details_from_db(session_id)
        if details:
            username = details["username"]
            department = details["department"]
    
    # SQL Agent
    agent_executor = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="openai-tools",
        verbose=True
    )

    # Prompt
    system_prompt = f"""
    You are an assistant helping users analyze and calculate data from a financial database.
    Always remember:
    - The current user is {username} from the {department} department.

    DATABASE SCHEMA:
    - non_payroll_budget: Budget data by account/department with monthly columns
    - payroll_budget: Employee salary budgets with monthly allocations
    - actual_tb_data: Trial balance with actual expenses, vendors, PO numbers
    - actual_timesheet_data: Employee timesheet entries with days and projects
    - Mapping tables: main_accounts, departments, projects, employees

    ANALYSIS GUIDELINES:
    - For Department Expense Analysis → compare non_payroll_budget vs actual_tb_data
    - For Timesheet Analysis → compare payroll_budget vs actual_timesheet_data
    - For expenses/costs/transactions → use `actual_tb_data`
    - For payroll/salaries → use `actual_timesheet_data`
    - Provide specific numbers, percentages, insights, and recommendations
    - Never hallucinate, always query the DB directly

    SCOPING RULES:
    - If the user asks a generic question (e.g., "What is the total expense?"), assume they mean their own department: {department}.
    - Do NOT show results for all departments unless the user explicitly asks for "all departments" or specifies another department name.
    - Always default filtering and aggregation to the user’s department unless overridden by explicit user instructions.
    """

    # Save user query
    save_to_memory(session_id, "user", user_query)

    # Load last 10 messages for context
    chat_history = load_from_memory(session_id)[-10:]
    history_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in chat_history])

    try:
        # Run query
        result = agent_executor.invoke({
            "input": f"""{system_prompt}

        Conversation History:
        {history_text}

        User query: {user_query}
        """
        })

        assistant_answer = result.get("output", "⚠️ No response from agent.")

        # Save response
        save_to_memory(session_id, "assistant", assistant_answer)

        return assistant_answer
        
    except Exception as e:
        error_message = f"Error processing query: {str(e)}"
        save_to_memory(session_id, "assistant", error_message)
        return error_message