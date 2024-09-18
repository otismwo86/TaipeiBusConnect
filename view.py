from fastapi.templating import Jinja2Templates
from fastapi import Request

# 設定模板目錄
templates = Jinja2Templates(directory="html")

def render_main_page(request: Request):
    """
    渲染主頁面
    """
    return templates.TemplateResponse("mainpage.html", {"request": request})

def render_bus_details_page(request: Request, route_name: str):
    """
    渲染公車詳細信息頁面
    """
    return templates.TemplateResponse("busdetails.html", {"request": request, "route_name": route_name})

def render_member_page(request: Request):
    """
    渲染會員頁面
    """
    return templates.TemplateResponse("memberpage.html", {"request": request})

def render_test_notification_page(request: Request):
    """
    渲染測試通知頁面
    """
    return templates.TemplateResponse("testnoti.html", {"request": request})

def render_chatroom_page(request: Request, route_name: str):
    """
    渲染聊天室頁面
    """
    return templates.TemplateResponse("chatroom.html", {"request": request, "route_name": route_name})

def render_favorites_page(request: Request):
    """
    渲染用戶的最愛頁面
    """
    return templates.TemplateResponse("favorites.html", {"request": request})

def render_subscription_page(request: Request):
    """
    渲染用戶訂閱頁面
    """
    return templates.TemplateResponse("subscription.html", {"request": request})

def render_upload_page(request: Request):
    """
    渲染圖片上傳頁面
    """
    return templates.TemplateResponse("upload.html", {"request": request})
