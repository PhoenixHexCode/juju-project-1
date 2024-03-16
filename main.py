from fastapi import FastAPI
from mangum import Mangum
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
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
    # system content string that will explain the role of the system
    system_content = "You are an expert veterinarian, offering detailed, empathetic guidance on various pets' health, behavior, nutrition, and care, helping pet owners understand and address their concerns with professional and supportive advice."
    
    # user content string that will be the user's question
    user_content = "Why is my dog throwing up?"
    
    # assistant response give a response that will guide the user to find out next steps to take to help their pet
    assistant_response = "Give the user 5 steps to take to help their pet in json format as step_[number] and the action to take as the value with max token as 50"
    
    
    completion = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_response},
        ],
        max_tokens=300,
        response_format={
            "type": "json_object"
        },
    )

    message = completion.choices[0].message
    content = json.loads(message.content)
    
    return {
        'chat': content,
        'total_tokens': completion.usage.total_tokens
    }

@app.post('/question')
async def question_response(request: Question):
    return request.question


handler = Mangum(app)
