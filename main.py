from fastapi import FastAPI
from mangum import Mangum
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from database import MySQLDatabase
import os
import json

# Load the .env file
load_dotenv()



client = OpenAI(
  api_key=os.environ.get("OPENAI_API_KEY"),
)

class Question(BaseModel):
    question: str


app = FastAPI()


@app.get("/")
def read_root():

    # Initialize database connection
    db = MySQLDatabase()

    # system content string that will explain the role of the system
    system_content = "You are an expert veterinarian, offering detailed, empathetic guidance on various pets' health, behavior, nutrition, and care, helping pet owners understand and address their concerns with professional and supportive advice."
    
    # user content string that will be the user's question
    user_content = "Why is my dog throwing up?"
    
    # assistant response give a response that will guide the user to find out next steps to take to help their pet
    assistant_response = "Give the user 5 steps to take to help their pet in json format as step_[number] and the action to take as the value with max token as 50"
    
    gpt_message = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_response},
    ]
    
    completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=gpt_message,
        max_tokens=300,
        response_format={
            "type": "json_object"
        },
    )
    
    
    total_tokens = completion.usage.total_tokens
    #Database needs message, response, tokens
    
    # Execute an insert query
    insert_query = "INSERT INTO token_usage (message, response, tokens) VALUES (%s, %s, %s)"
    db.execute_query(insert_query, (json.dumps(gpt_message), None, total_tokens))
    
    # Close the connection
    db.close()

    message = completion.choices[0].message
    content = json.loads(message.content)
    
    return {
        'chat': content,
        'total_tokens': total_tokens
    }

#Create new app.get
#  url dynamic parameter base
#  /token/1
@app.get('/token/{id}')
async def get_token_by_id(id: int):

    print('get_token_by_id', id)    
    #Retreive id infromation
    # Initialize database connection
    db = MySQLDatabase()

    # Execute a select query
    select_query = """
        SELECT tokens, message, created_at FROM token_usage WHERE id = %s 
        """
    db_result = db.execute_select_query(select_query, (id,))

    if not db_result:
        return None

    result = db_result[0]

    #PRINT INFORMATION WITHOUT LIST NAME / ARRAY
    # for row in db_result:
    #     result_value = row[0]

    # Close the connection
    db.close()

    return result['tokens']


@app.post('/question')
async def question_response(request: Question):
    return request.question


handler = Mangum(app)
