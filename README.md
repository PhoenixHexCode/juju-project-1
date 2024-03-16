# VetPetAI-API

## Steps for local hosting: 
### (example from url: https://levelup.gitconnected.com/the-easiest-way-to-deploy-a-python-api-aws-serverless-222efa0f13c8)
1. Deploy FastAPI App
    - Set up a virtual environment:
```python3 -m venv myenv```  One per machine/project

    - Activate the virtual environment:
```myenv\Scripts\activate```

    - Install python required libraries from requirements.txt
```pip install -r requirements.txt``` 

    - Create a FastAPI app:
        Create a new Python file, for example main.py, and open it in a text editor. Import necessary modules and set up the app:
```python
from fastapi import FastAPI
app = FastAPI()
```

    - Define your API endpoints:
        Add route definitions and corresponding functions to handle requests. For example:
```python
@app.get("/")
def read_root():
    return {"Hello": "World"}
```

    - Test your app locally:
        Start the development server with Uvicorn:

```uvicorn main:app --reload --host [your_ip_address] --port 8000```

        Open your browser and visit http://localhost:8000 to see the "Hello World" message.

    - Configure your app for deployment with Mangum:
        Install the Mangum library:

        Update your main.py file:

```python
from fastapi import FastAPI
from mangum import Mangum

app = FastAPI()
@app.get("/")
def read_root():
    return {"Hello": "World"}
handler = Mangum(app)
```


    - Install serverless
```npm install serverless```
```npm install serverless-python-requirements```

    - Login into AWS CLI
```aws configure```

    - Configure requirements.txt file
```pip freeze >> requirements.txt```

    - Setup a serverless.yml file
        Create a serverless.yml file with following content:
```
service: your-service-name

plugins:
  - serverless-python-requirements


provider:
  name: aws
  runtime: python3.8
  timeout: 30
  region: us-west-1

functions:
  app:
    handler: main.handler
  
    events:
      - http:
          method: any
          path: /{proxy+}
          
      - http:
          method: any
          path: /
```
          
This should deploy your app to AWS Lambda + API Gateway.