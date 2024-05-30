from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Annotated
import models
from database import Base, engine, SessionLocal
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import json
from datetime import datetime, timedelta

import cv2
from multiprocessing import Pool
import os
import uuid
import cv2
from ultralytics import YOLO
 
IMAGEDIR = "images/"
 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

current_date = datetime.now().date()

class UserBase(BaseModel):
    username:str
    email:str
    password:str

class AchievementBase(BaseModel):
    id : int
    plastic: int
    paper: int
    cardboard: int
    metal: int
    glass: int
    total: int

class UserLogin(BaseModel):
    username:str
    password:str

class ImageBase(BaseModel):
    name:str
    user_id:int
    result:str
    date:str

class ImageUpdate(BaseModel):
    name:str
    data:dict

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

 
@app.post("/register/")
async def register_user(user:UserBase, db: db_dependency):
    user.password = pwd_context.hash(user.password)  
    db_user = models.User(**user.dict())
    db.add(db_user)
    db.commit()
    userQuery = db.query(models.User).filter(models.User.username == db_user.username).first()
    db_achievement = models.Achievement(id=userQuery.id,
        plastic=0,
        paper=0,
        cardboard=0,
        metal=0,
        glass=0,
        total=0)
    db.add(db_achievement)
    db.commit()


@app.post("/login/")
async def login_user(userlogin:UserLogin, db: db_dependency):
    user = db.query(models.User).filter(models.User.username == userlogin.username).first()
    if not user or not pwd_context.verify(userlogin.password, user.password ):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"message": "Login successful", "user_id": user.id, "username":user.username}

@app.post("/upload/")
async def create_upload_file(user_id:int, db: db_dependency, file: UploadFile = File(...)):
 
    file.filename = f"{uuid.uuid4()}.jpg"
    contents = await file.read()
 
    #save the file
    with open(f"{IMAGEDIR}{file.filename}", "wb") as f:
        f.write(contents)
    
    result = prediction(IMAGEDIR+file.filename)
    db_achievement = db.query(models.Achievement).filter(models.Achievement.id == user_id).first()
    db_achievement.plastic += result['plastic']['q']
    db_achievement.paper += result['paper']['q']
    db_achievement.cardboard += result['cardboard']['q']
    db_achievement.metal += result['metal']['q']
    db_achievement.glass += result['glass']['q']
    db_achievement.total = db_achievement.plastic + db_achievement.paper +db_achievement.cardboard +db_achievement.metal +db_achievement.glass

    db_upload = models.Image(name = file.filename, user_id = user_id, result = json.dumps(result), date = current_date.strftime("%Y-%m-%d") )
    db.add(db_upload)
    db.commit()

    return {"filename": file.filename, "result":result}
 
 
# @app.get("/show/{image_id}")
# async def read_image(image_id : str):

#     path = f"{IMAGEDIR}{image_id}"
     
#     return FileResponse(path)

@app.get("/get_image/{image_request}")
async def get_image(image_request: str):
    image_path = os.path.join(IMAGEDIR, image_request)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


@app.get("/show/{user_id}")
async def read_image(user_id : int, db: db_dependency):
    all_images = []
    images = db.query(models.Image).filter(models.Image.user_id == user_id).all()
    for i in images:
        all_images.append(json.dumps({'name':i.name,'result':json.loads(i.result), 'date': i.date.strftime("%Y-%m-%d")}))
    return all_images

    # path = f"{IMAGEDIR}{image_id}"
     
    # return FileResponse(path)

@app.get("/show_achievement/{user_id}")
async def read_achievement(user_id : int, db: db_dependency):
    achievement = db.query(models.Achievement).filter(models.Achievement.id == user_id).first()
    return achievement

@app.post("/update/")
async def update_data(data: ImageUpdate, db: db_dependency):
    db_data = db.query(models.Image).filter(models.Image.name == data.name).first()
    db_data.result = json.dumps(data.data)
    db.commit()

#MONTHLY QUANTITY
@app.get("/show/monthlyquantity/{user_id}")
async def show_monthly_quantity(user_id : int, db: db_dependency):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    all_images = []
    months = []
    chartData = [{'name': 'Cardboard', 'data' : []},
                {'name': 'Paper', 'data' : []},
                {'name': 'Plastic', 'data' : []},
                {'name': 'Glass', 'data' : []},
                {'name': 'Metal', 'data' : []}]
    images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
    for image in images:
        month = image.date.strftime("%B")
        if month not in months:
            months.append(month)
            for data in chartData:
                data['data'].append(0)
        result = json.loads(image.result)
        monthIndex = months.index(month)
        for i in chartData:
            if i['name'] == 'Cardboard':
                i['data'][monthIndex] += result['cardboard']['q']
            elif i['name'] == 'Paper':
                i['data'][monthIndex] += result['paper']['q']
            elif i['name'] == 'Plastic':
                i['data'][monthIndex] += result['plastic']['q']
            elif i['name'] == 'Glass':
                i['data'][monthIndex] += result['glass']['q']
            elif i['name'] == 'Metal':
                i['data'][monthIndex] += result['metal']['q']

    return (json.dumps({'xAxis': months, 'data': chartData}))


#MONTHLY SAVED CARBON
@app.get("/show/monthly/{user_id}")
async def show_monthly(user_id : int, db: db_dependency):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    all_images = []
    months = []
    carbonEmission= {'Cardboard':1, 'Paper':0.4, 'Plastic': 0.8, 'Glass': 0.4, 'Metal':0.7}
    chartData = [{'name': 'Cardboard', 'data' : []},
                {'name': 'Paper', 'data' : []},
                {'name': 'Plastic', 'data' : []},
                {'name': 'Glass', 'data' : []},
                {'name': 'Metal', 'data' : []}]
    images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
    for image in images:
        month = image.date.strftime("%B")
        if month not in months:
            months.append(month)
            for data in chartData:
                data['data'].append(0)
        result = json.loads(image.result)
        monthIndex = months.index(month)
        for i in chartData:
            if i['name'] == 'Cardboard':
                i['data'][monthIndex] += ((result['cardboard']['w']/1000) * carbonEmission['Cardboard'])
            elif i['name'] == 'Paper':
                i['data'][monthIndex] += ((result['paper']['w']/1000) * carbonEmission['Paper'])
            elif i['name'] == 'Plastic':
                i['data'][monthIndex] += ((result['plastic']['w']/1000) * carbonEmission['Plastic'])
            elif i['name'] == 'Glass':
                i['data'][monthIndex] += ((result['glass']['w']/1000) * carbonEmission['Glass'])
            elif i['name'] == 'Metal':
                i['data'][monthIndex] += ((result['metal']['w']/1000) * carbonEmission['Metal'])

    return (json.dumps({'xAxis': months, 'data': chartData}))



# MONTHLY COMPARISON CARBON
# @app.get("/show/monthly/{user_id}")
# async def read_image(user_id : int, db: db_dependency):
#     end_date = datetime.now()
#     start_date = end_date - timedelta(days=180)
#     all_images = []
#     months = []
#     carbonEmission= {'Cardboard':0.15, 'Paper':0.11, 'Plastic': 0.21, 'Glass': 0.09, 'Metal':1.1}
#     carbonEmissionRecycle= {'Cardboard':0.05, 'Paper':0.07, 'Plastic': 0.13, 'Glass': 0.05, 'Metal':0.04}
#     chartData = [{'name': 'Cardboard', 'data' : [], 'stack': 'cardboard'},
#                 {'name': 'Paper', 'data' : [], 'stack': 'paper'},
#                 {'name': 'Plastic', 'data' : [], 'stack': 'plastic'},
#                 {'name': 'Glass', 'data' : [], 'stack': 'glass'},
#                 {'name': 'Metal', 'data' : [], 'stack': 'metal'}]
#     chartDataRecycle = [{'name': 'Recycled Cardboard', 'data' : [], 'stack': 'cardboard'},
#                 {'name': 'Recycled Paper', 'data' : [], 'stack': 'paper'},
#                 {'name': 'Recycled Plastic', 'data' : [], 'stack': 'plastic'},
#                 {'name': 'Recycled Glass', 'data' : [], 'stack': 'glass'},
#                 {'name': 'Recycled Metal', 'data' : [], 'stack': 'metal'}]
#     images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
#     for image in images:
#         month = image.date.strftime("%B")
#         if month not in months:
#             months.append(month)
#             for data in chartData:
#                 data['data'].append(0)
#             for data in chartDataRecycle:
#                 data['data'].append(0)
#         result = json.loads(image.result)
#         monthIndex = months.index(month)
#         for i in chartData:
#             if i['name'] == 'Cardboard':
#                 i['data'][monthIndex] += (result['cardboard'] * carbonEmission['Cardboard'])
#             elif i['name'] == 'Paper':
#                 i['data'][monthIndex] += (result['paper'] * carbonEmission['Paper'])
#             elif i['name'] == 'Plastic':
#                 i['data'][monthIndex] += (result['plastic'] * carbonEmission['Plastic'])
#             elif i['name'] == 'Glass':
#                 i['data'][monthIndex] += (result['glass'] * carbonEmission['Glass'])
#             elif i['name'] == 'Metal':
#                 i['data'][monthIndex] += (result['metal'] * carbonEmission['Metal'])
#         for i in chartDataRecycle:
#             if i['name'] == 'Recycled Cardboard':
#                 i['data'][monthIndex] += (result['cardboard'] * carbonEmissionRecycle['Cardboard'])
#             elif i['name'] == 'Recycled Paper':
#                 i['data'][monthIndex] += (result['paper'] * carbonEmissionRecycle['Paper'])
#             elif i['name'] == 'Recycled Plastic':
#                 i['data'][monthIndex] += (result['plastic'] * carbonEmissionRecycle['Plastic'])
#             elif i['name'] == 'Recycled Glass':
#                 i['data'][monthIndex] += (result['glass'] * carbonEmissionRecycle['Glass'])
#             elif i['name'] == 'Recycled Metal':
#                 i['data'][monthIndex] += (result['metal'] * carbonEmissionRecycle['Metal'])
#     return (json.dumps({'xAxis': months, 'data': chartData + chartDataRecycle}))

# DAILY QUANTITY
@app.get("/show/dailyquantity/{user_id}")
async def show_daily_quantity(user_id : int, db: db_dependency):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    all_images = []
    days = []
    chartData = [{'name': 'Cardboard', 'data' : []},
                {'name': 'Paper', 'data' : []},
                {'name': 'Plastic', 'data' : []},
                {'name': 'Glass', 'data' : []},
                {'name': 'Metal', 'data' : []}]
    images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
    for image in images:
        day = image.date.strftime("%A")
        if day not in days:
            days.append(day)
            for data in chartData:
                data['data'].append(0)
        result = json.loads(image.result)
        dayIndex = days.index(day)
        for i in chartData:
            if i['name'] == 'Cardboard':
                i['data'][dayIndex] += result['cardboard']['q']
            elif i['name'] == 'Paper':
                i['data'][dayIndex] += result['paper']['q']
            elif i['name'] == 'Plastic':
                i['data'][dayIndex] += result['plastic']['q']
            elif i['name'] == 'Glass':
                i['data'][dayIndex] += result['glass']['q']
            elif i['name'] == 'Metal':
                i['data'][dayIndex] += result['metal']['q']

    return (json.dumps({'xAxis': days, 'data': chartData}))


# DAILY SAVED CARBON
@app.get("/show/daily/{user_id}")
async def show_daily(user_id : int, db: db_dependency):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    all_images = []
    days = []
    carbonEmission= {'Cardboard':1, 'Paper':0.4, 'Plastic': 0.8, 'Glass': 0.4, 'Metal':0.7}
    chartData = [{'name': 'Cardboard', 'data' : []},
                {'name': 'Paper', 'data' : []},
                {'name': 'Plastic', 'data' : []},
                {'name': 'Glass', 'data' : []},
                {'name': 'Metal', 'data' : []}]
    images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
    for image in images:
        day = image.date.strftime("%A")
        if day not in days:
            days.append(day)
            for data in chartData:
                data['data'].append(0)
        result = json.loads(image.result)
        dayIndex = days.index(day)
        for i in chartData:
            if i['name'] == 'Cardboard':
                i['data'][dayIndex] += ((result['cardboard']['w']/1000) * carbonEmission['Cardboard'])
            elif i['name'] == 'Paper':
                i['data'][dayIndex] += ((result['paper']['w']/1000) * carbonEmission['Paper'])
            elif i['name'] == 'Plastic':
                i['data'][dayIndex] += ((result['plastic']['w']/1000) * carbonEmission['Plastic'])
            elif i['name'] == 'Glass':
                i['data'][dayIndex] += ((result['glass']['w']/1000) * carbonEmission['Glass'])
            elif i['name'] == 'Metal':
                i['data'][dayIndex] += ((result['metal']['w']/1000) * carbonEmission['Metal'])

    return (json.dumps({'xAxis': days, 'data': chartData}))

# DAILY COMPARISON CARBON
# @app.get("/show/daily/{user_id}")
# async def read_image_daily(user_id : int, db: db_dependency):
#     end_date = datetime.now()
#     start_date = end_date - timedelta(days=7)
#     all_images = []
#     days = []
#     carbonEmission= {'Cardboard':0.15, 'Paper':0.11, 'Plastic': 0.21, 'Glass': 0.09, 'Metal':1.1}
#     carbonEmissionRecycle= {'Cardboard':0.05, 'Paper':0.07, 'Plastic': 0.13, 'Glass': 0.05, 'Metal':0.04}
#     chartData = [{'name': 'Cardboard', 'data' : [], 'stack': 'cardboard'},
#                 {'name': 'Paper', 'data' : [], 'stack': 'paper'},
#                 {'name': 'Plastic', 'data' : [], 'stack': 'plastic'},
#                 {'name': 'Glass', 'data' : [], 'stack': 'glass'},
#                 {'name': 'Metal', 'data' : [], 'stack': 'metal'}]
#     chartDataRecycle = [{'name': 'Recycled Cardboard', 'data' : [], 'stack': 'cardboard'},
#                 {'name': 'Recycled Paper', 'data' : [], 'stack': 'paper'},
#                 {'name': 'Recycled Plastic', 'data' : [], 'stack': 'plastic'},
#                 {'name': 'Recycled Glass', 'data' : [], 'stack': 'glass'},
#                 {'name': 'Recycled Metal', 'data' : [], 'stack': 'metal'}]
#     images = db.query(models.Image).filter(models.Image.user_id == user_id, models.Image.date.between(start_date, end_date)).all()
#     for image in images:
#         day = image.date.strftime("%A")
#         if day not in days:
#             days.append(day)
#             for data in chartData:
#                 data['data'].append(0)
#             for data in chartDataRecycle:
#                 data['data'].append(0)
#         result = json.loads(image.result)
#         dayIndex = days.index(day)
#         for i in chartData:
#             if i['name'] == 'Cardboard':
#                 i['data'][dayIndex] += (result['cardboard'] * carbonEmission['Cardboard'])
#             elif i['name'] == 'Paper':
#                 i['data'][dayIndex] += (result['paper'] * carbonEmission['Paper'])
#             elif i['name'] == 'Plastic':
#                 i['data'][dayIndex] += (result['plastic'] * carbonEmission['Plastic'])
#             elif i['name'] == 'Glass':
#                 i['data'][dayIndex] += (result['glass'] * carbonEmission['Glass'])
#             elif i['name'] == 'Metal':
#                 i['data'][dayIndex] += (result['metal'] * carbonEmission['Metal'])
#         for i in chartDataRecycle:
#             if i['name'] == 'Recycled Cardboard':
#                 i['data'][dayIndex] += (result['cardboard'] * carbonEmissionRecycle['Cardboard'])
#             elif i['name'] == 'Recycled Paper':
#                 i['data'][dayIndex] += (result['paper'] * carbonEmissionRecycle['Paper'])
#             elif i['name'] == 'Recycled Plastic':
#                 i['data'][dayIndex] += (result['plastic'] * carbonEmissionRecycle['Plastic'])
#             elif i['name'] == 'Recycled Glass':
#                 i['data'][dayIndex] += (result['glass'] * carbonEmissionRecycle['Glass'])
#             elif i['name'] == 'Recycled Metal':
#                 i['data'][dayIndex] += (result['metal'] * carbonEmissionRecycle['Metal'])

#     return (json.dumps({'xAxis': days, 'data': chartData + chartDataRecycle}))

def prediction(image_name):
    result_dict = {'cardboard':{"q":0,"w":0}, 'paper': {"q":0,"w":0}, 'plastic': {"q":0,"w":0}, 'glass': {"q":0,"w":0}, 'metal': {"q":0,"w":0}}
    model = YOLO('best.pt')
    images = image_name
    image = cv2.imread(images)
    results = model.predict(images,imgsz=640,conf=0.5,iou=0.45)
    results = results[0]
    color = {0: (0, 102, 255), 1: (50, 205, 50), 2:(255, 92, 92), 3: (255, 255, 85), 4: (153, 50, 204)}  
    border_thickness = 15  # Fixed thickness for rectangles and text
    font_thickness = 10
    font_scale = 4  # Fixed font scale for text
    for i in range(len(results.boxes)):
        box = results.boxes[i]
        prob = round(box.conf[0].item(), 2)
        class_id = box.cls[0].item()
        name = results.names[class_id]
        tensor = box.xyxy[0]
        x1 = int(tensor[0].item())
        y1 = int(tensor[1].item())
        x2 = int(tensor[2].item())
        y2 = int(tensor[3].item())
        cv2.rectangle(image,(x1,y1),(x2,y2),color[class_id], thickness=border_thickness)
        cv2.putText(image, name + " " + str(prob), (x1, y1-30), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color[class_id], thickness=font_thickness)
        result_dict[name]['q'] +=1
        result_dict[name]['w'] += 100
    cv2.imwrite(images, image)
    return result_dict
