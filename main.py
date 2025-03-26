import os
import pathlib
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from database import create_db, engine
from seeder import seed
from models import *
from sqlmodel import SQLModel, Session, select, func, case
from typing import List, Optional
from urllib.parse import parse_qs

app = FastAPI()

current_file_path = pathlib.Path(__file__).parent.resolve()
templates = Jinja2Templates(directory=os.path.join(current_file_path, "templates"))

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def parse_form_data(body: str) -> dict:
    """Parse form data from request body"""
    if not body:
        return {}
    return {k: v[0] for k, v in parse_qs(body).items()}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    with Session(engine) as session:
        # Get basic counts
        users_count = len(session.exec(select(User)).all())
        subscriptions_count = len(session.exec(select(Subscriptions)).all())
        subscription_types_count = len(session.exec(select(SubType)).all())
        
        # Get recent users and subscriptions
        recent_users = session.exec(select(User).order_by(User.id.desc()).limit(5)).all()
        recent_subscriptions = session.exec(
            select(Subscriptions)
            .join(User)
            .join(SubType)
            .order_by(Subscriptions.id.desc())
            .limit(5)
        ).all()

        # Get all subscription types
        subscription_types = session.exec(select(SubType)).all()
        
        # Get aggregated subscription data
        subscription_data = []
        users = session.exec(select(User)).all()
        
        for user in users:
            user_subs = session.exec(
                select(Subscriptions)
                .where(Subscriptions.user_id == user.id)
            ).all()
            
            if user_subs:
                total_users = sum(sub.users_count for sub in user_subs)
                total_discount = sum(sub.discount * sub.users_count for sub in user_subs)
                notes = [sub.notes for sub in user_subs if sub.notes]
                
                # Create type counts and discounts dictionary
                type_counts = {}
                type_discounts = {}
                for st in subscription_types:
                    type_subs = [sub for sub in user_subs if sub.sub_type_id == st.id]
                    type_counts[st.name] = sum(sub.users_count for sub in type_subs)
                    type_discounts[st.name] = sum(sub.discount * sub.users_count for sub in type_subs)
                
                subscription_data.append({
                    'username': user.username,
                    'total_users': total_users,
                    'total_discount': total_discount,
                    'notes': notes,
                    'type_counts': type_counts,
                    'type_discounts': type_discounts
                })
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "users_count": users_count,
                "subscriptions_count": subscriptions_count,
                "subscription_types_count": subscription_types_count,
                "recent_users": recent_users,
                "recent_subscriptions": recent_subscriptions,
                "subscription_data": subscription_data,
                "subscription_types": subscription_types
            }
        )

@app.get("/users", response_class=HTMLResponse)
async def list_users(request: Request):
    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.name)).all()
        return templates.TemplateResponse(
            "table.html",
            {
                "request": request,
                "users": users,
                "title": "Users"
            }
        )

@app.post("/users", response_class=HTMLResponse)
async def create_user(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        user = User(
            username=data["username"],
            name=data["name"],
            phone=data["phone"],
            notes=data.get("notes", "")
        )
        session.add(user)
        session.commit()
        return templates.TemplateResponse(
            "partials/user_row.html",
            {
                "request": request,
                "user": user
            }
        )

@app.get("/users/{user_id}", response_class=HTMLResponse)
async def get_user(request: Request, user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        types = session.exec(select(SubType)).all()
        return templates.TemplateResponse(
            "user_detail.html",
            {
                "request": request,
                "user": user,
                "types": types
            }
        )

@app.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def get_user_edit_form(request: Request, user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return templates.TemplateResponse(
            "partials/user_edit_form.html",
            {
                "request": request,
                "user": user
            }
        )

@app.post("/users/{user_id}")
@app.put("/users/{user_id}")
async def update_user(request: Request, user_id: int):
    # Try to get data as form data first
    try:
        form_data = await request.form()
        data = dict(form_data)
    except:
        # If not form data, try to get as JSON
        data = await request.json()
    
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update only the fields that are present in the data
        if "username" in data:
            user.username = data["username"]
        if "name" in data:
            user.name = data["name"]
        if "phone" in data:
            user.phone = data["phone"]
        if "notes" in data:
            user.notes = data["notes"]
            
        session.commit()

        # Check if this is a request from the user info page (expecting JSON)
        if "hx-target" in request.headers and request.headers["hx-target"] == "body":
            return JSONResponse({
                "username": user.username,
                "name": user.name,
                "phone": user.phone,
                "notes": user.notes
            })
        
        # For the users table page, return the updated row HTML
        return templates.TemplateResponse(
            "partials/user_row.html",
            {
                "request": request,
                "user": user
            }
        )

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user has any subscriptions
        user_subs = session.exec(
            select(Subscriptions)
            .where(Subscriptions.user_id == user_id)
        ).first()
        
        if user_subs:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete user with active subscriptions. Please delete all subscriptions first."
            )
            
        session.delete(user)
        session.commit()
        return JSONResponse(
            content={"message": "User deleted successfully"},
            status_code=200,
            headers={"HX-Trigger": "userDeleted"}
        )

@app.get("/subscriptions", response_class=HTMLResponse)
async def list_subscriptions(request: Request):
    with Session(engine) as session:
        subscriptions = session.exec(
            select(Subscriptions)
            .join(User)
            .join(SubType)
            .order_by(User.name)
        ).all()
        users = session.exec(select(User)).all()
        types = session.exec(select(SubType)).all()
        return templates.TemplateResponse(
            "table.html",
            {
                "request": request,
                "subscriptions": subscriptions,
                "users": users,
                "types": types,
                "title": "Subscriptions"
            }
        )

@app.post("/subscriptions", response_class=HTMLResponse)
async def create_subscription(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        subscription = Subscriptions(
            user_id=int(data["user_id"]),
            users_count=int(data["users_count"]),
            discount=int(data["discount"]),
            sub_type_id=int(data["sub_type_id"]),
            notes=data.get("notes", "")
        )
        session.add(subscription)
        session.commit()
        return templates.TemplateResponse(
            "partials/subscription_row.html",
            {
                "request": request,
                "subscription": subscription
            }
        )

@app.get("/subscriptions/{sub_id}/edit", response_class=HTMLResponse)
async def get_subscription_edit_form(request: Request, sub_id: int):
    with Session(engine) as session:
        subscription = session.get(Subscriptions, sub_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        users = session.exec(select(User)).all()
        types = session.exec(select(SubType)).all()
        return templates.TemplateResponse(
            "partials/subscription_edit_form.html",
            {
                "request": request,
                "subscription": subscription,
                "users": users,
                "types": types
            }
        )

@app.put("/subscriptions/{sub_id}", response_class=HTMLResponse)
async def update_subscription(request: Request, sub_id: int):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        subscription = session.get(Subscriptions, sub_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        for key, value in data.items():
            if key in ['user_id', 'sub_type_id', 'users_count', 'discount']:
                value = int(value)
            setattr(subscription, key, value)
        session.commit()
        return templates.TemplateResponse(
            "partials/subscription_row.html",
            {
                "request": request,
                "subscription": subscription
            },
            headers={"HX-Trigger": "subscriptionUpdated"}
        )

@app.delete("/subscriptions/{sub_id}")
async def delete_subscription(sub_id: int):
    with Session(engine) as session:
        subscription = session.get(Subscriptions, sub_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        session.delete(subscription)
        session.commit()
        return JSONResponse(content={}, status_code=204)

@app.get("/subscription-types", response_class=HTMLResponse)
async def list_subscription_types(request: Request):
    with Session(engine) as session:
        types = session.exec(select(SubType)).all()
        return templates.TemplateResponse(
            "table.html",
            {
                "request": request,
                "types": types,
                "title": "Subscription Types"
            }
        )

@app.get("/subscription-types/{type_id}/edit", response_class=HTMLResponse)
async def get_subscription_type_edit_form(request: Request, type_id: int):
    with Session(engine) as session:
        sub_type = session.get(SubType, type_id)
        if not sub_type:
            raise HTTPException(status_code=404, detail="Subscription type not found")
        return templates.TemplateResponse(
            "partials/subscription_type_edit_form.html",
            {
                "request": request,
                "sub_type": sub_type
            }
        )

@app.post("/subscription-types", response_class=HTMLResponse)
async def create_subscription_type(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        sub_type = SubType(
            name=data["name"]
        )
        session.add(sub_type)
        session.commit()
        return templates.TemplateResponse(
            "partials/subscription_type_row.html",
            {
                "request": request,
                "sub_type": sub_type
            }
        )

@app.put("/subscription-types/{type_id}", response_class=HTMLResponse)
async def update_subscription_type(request: Request, type_id: int):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        sub_type = session.get(SubType, type_id)
        if not sub_type:
            raise HTTPException(status_code=404, detail="Subscription type not found")
        for key, value in data.items():
            setattr(sub_type, key, value)
        session.commit()
        return templates.TemplateResponse(
            "partials/subscription_type_row.html",
            {
                "request": request,
                "sub_type": sub_type
            },
            headers={"HX-Trigger": "subscriptionTypeUpdated"}
        )

@app.delete("/subscription-types/{type_id}")
async def delete_subscription_type(type_id: int):
    with Session(engine) as session:
        sub_type = session.get(SubType, type_id)
        if not sub_type:
            raise HTTPException(status_code=404, detail="Subscription type not found")
        session.delete(sub_type)
        session.commit()
        return JSONResponse(content={}, status_code=204)

@app.get("/users/{user_id}/info", response_class=HTMLResponse)
async def get_user_info(request: Request, user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return templates.TemplateResponse(
            "user_info.html",
            {
                "request": request,
                "user": user
            }
        )

@app.get("/ips/new", response_class=HTMLResponse)
async def get_new_ip_form(request: Request):
    # Get user_id from query parameters instead of form data
    user_id = request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    with Session(engine) as session:
        user = session.get(User, int(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return templates.TemplateResponse(
            "partials/ip_form.html",
            {
                "request": request,
                "user": user
            }
        )

@app.get("/ips/{ip_id}/edit", response_class=HTMLResponse)
async def get_ip_edit_form(request: Request, ip_id: int):
    with Session(engine) as session:
        ip = session.get(Ips, ip_id)
        if not ip:
            raise HTTPException(status_code=404, detail="IP not found")
        return templates.TemplateResponse(
            "partials/ip_edit_form.html",
            {
                "request": request,
                "ip": ip,
                "user": ip.user
            }
        )

@app.post("/ips", response_class=HTMLResponse)
async def create_ip(request: Request):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        ip = Ips(
            ip=data["ip"],
            name=data["name"],
            user_id=int(data["user_id"])
        )
        session.add(ip)
        session.commit()
        return templates.TemplateResponse(
            "partials/ip_row.html",
            {
                "request": request,
                "ip": ip
            }
        )

@app.post("/ips/{ip_id}")
@app.put("/ips/{ip_id}")
async def update_ip(request: Request, ip_id: int):
    form_data = await request.form()
    data = dict(form_data)
    with Session(engine) as session:
        ip = session.get(Ips, ip_id)
        if not ip:
            raise HTTPException(status_code=404, detail="IP not found")
        
        ip.ip = data["ip"]
        ip.name = data["name"]
        session.commit()
        
        return templates.TemplateResponse(
            "partials/ip_row.html",
            {
                "request": request,
                "ip": ip
            }
        )

@app.delete("/ips/{ip_id}")
async def delete_ip(ip_id: int):
    with Session(engine) as session:
        ip = session.get(Ips, ip_id)
        if not ip:
            raise HTTPException(status_code=404, detail="IP not found")
        
        session.delete(ip)
        session.commit()
        return JSONResponse(
            content={"message": "IP deleted successfully"},
            status_code=200
        )

if __name__ == '__main__':
    import uvicorn
    create_db()
    with Session(engine) as session:
        if not session.exec(select(SubType)).all():
            seed()
    uvicorn.run(app, host="127.0.0.1", port=8000)