from pickletools import string1
from common import *
from database import get_db
from dataclasses import dataclass
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import models

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals['get_selected'] = get_selected
templates.env.globals["generate_one_time_token"] = generate_one_time_token


@dataclass
class QaContentDataclass:
    """
    1:1문의 폼 데이터
    """
    qa_email: str = Form(None)
    qa_hp: str = Form(None)
    qa_type: int = 0
    qa_category: str = Form(...)
    qa_email_recv: bool = Form(None)
    qa_sms_recv: bool = Form(None)
    qa_html: int = Form(None)
    qa_subject: str = Form(...)
    qa_content: str = Form(...)
    qa_file1: UploadFile = File(None),
    qa_file2: UploadFile = File(None),


@router.get("/list")
def qa_list(request: Request,
            db: Session = Depends(get_db)):
    '''
    Q&A 목록 보기
    '''
    sca = request.state.sca if request.state.sca is not None else ""
    stx = request.state.stx if request.state.stx is not None else ""

    # Q&A 설정 조회
    qa_config = db.query(models.QaConfig).order_by(models.QaConfig.id.asc()).first()
    if not qa_config:
        raise HTTPException(status_code=404, detail=f"Q&A Config is not found.")
    
    # Q&A 목록 조회
    queryset = db.query(models.QaContent).filter(models.QaContent.qa_type == 0).order_by(models.QaContent.qa_id.desc())
    # 제목과 내용 중 검색어가 있으면 검색한다.
    if sca:
        queryset = queryset.filter(models.QaContent.qa_category == sca)
    if stx:
        queryset = queryset.filter(models.QaContent.qa_subject.like(f"%{stx}%") | models.QaContent.qa_content.like(f"%{stx}%"))
    qa_list = queryset.all()

    context = {
        "request": request,
        "outlogin": request.state.context["outlogin"],
        "qa_list": qa_list,
        "categories": qa_config.qa_category.split("|"),
    }

    return templates.TemplateResponse(f"qa/pc/qa_list.html", context)


@router.get("/write")
def qa_write(request: Request,
             db: Session = Depends(get_db)):
    '''
    Q&A 작성하기
    '''
    # Q&A 설정 조회
    qa_config = db.query(models.QaConfig).order_by(models.QaConfig.id.asc()).first()
    if not qa_config:
        raise HTTPException(status_code=404, detail=f"Q&A Config is not found.")

    context = {
        "request": request,
        "outlogin": request.state.context["outlogin"],
        "categories": qa_config.qa_category.split("|"),
        "qa": None,
    }

    return templates.TemplateResponse(f"qa/pc/qa_form.html", context)


# Q&A 수정하기
@router.get("/write/{qa_id:int}")
def qa_edit(qa_id: int,
            request: Request,
            db: Session = Depends(get_db)):
    '''
    Q&A 수정하기
    '''
    # Q&A 설정 조회
    qa_config = db.query(models.QaConfig).order_by(models.QaConfig.id.asc()).first()
    if not qa_config:
        raise HTTPException(status_code=404, detail=f"Q&A Config is not found.")

    # Q&A 상세 조회
    qa = db.query(models.QaContent).filter(models.QaContent.qa_id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail=f"{qa_id} is not found.")

    context = {
        "request": request,
        "outlogin": request.state.context["outlogin"],
        "categories": qa_config.qa_category.split("|"),
        "qa": qa,
    }

    return templates.TemplateResponse(f"qa/pc/qa_form.html", context)


@router.post("/update")
def qa_update(request: Request,
                token: str = Form(...),
                qa_id: str = Form(None),
                db: Session = Depends(get_db),
                form_data: QaContentDataclass = Depends()
                ):
    """1:1문의 설정 등록/수정 처리

    Args:
        token (str): 입력/수정/삭제 변조 방지 토큰.
        form_data (QaConfigDataclass): 입력/수정 Form Data.

    Raises:
        HTTPException: 토큰 유효성 검사

    Returns:
        RedirectResponse: 1:1문의 설정 등록/수정 후 폼으로 이동
    """
    # 회원정보

    if validate_one_time_token(token, 'create'): # 토큰에 등록돤 action이 create라면 신규 등록
        form_data.mb_id = ''
        form_data.qa_name = ''
        form_data.qa_datetime = datetime.now()
        form_data.qa_ip = ''

        qa = models.QaContent(**form_data.__dict__)
        db.add(qa)
        db.commit()

    elif validate_one_time_token(token, 'update'):  # 토큰에 등록된 action이 create가 아니라면 수정
        # 데이터 수정 후 commit
        qa = db.query(models.QaContent).filter(models.QaContent.qa_id == qa_id).first()
        for field, value in form_data.__dict__.items():
            setattr(qa, field, value)
        db.commit()
    
    else: # 토큰 검사 실패
        raise HTTPException(status_code=404, detail=f"{token} : 토큰이 존재하지 않습니다.")

    return RedirectResponse(url=f"/qa/{qa.qa_id}", status_code=302)


@router.get("/delete/{qa_id}")
def qa_delete(qa_id: int,
              token: str = Query(...),
              db: Session = Depends(get_db)):
    '''
    Q&A 삭제하기
    '''
    if not validate_one_time_token(token, 'delete'):
        raise HTTPException(status_code=404, detail=f"{token} : 토큰이 존재하지 않습니다.")


    # Q&A 삭제
    db.query(models.QaContent).filter(models.QaContent.qa_id == qa_id).delete()
    db.commit()

    return RedirectResponse(url=f"/qa/list", status_code=302)


@router.get("/{qa_id}")
def qa_view(qa_id: int,
            request: Request,
            db: Session = Depends(get_db)):
    '''
    Q&A 상세보기
    '''
    model = models.QaContent

    # Q&A 설정 조회
    qa_config = db.query(models.QaConfig).order_by(models.QaConfig.id.asc()).first()
    if not qa_config:
        raise HTTPException(status_code=404, detail=f"Q&A Config is not found.")
    
    # Q&A 조회
    qa = db.query(model).filter(model.qa_id == qa_id).first()

    # Q&A 답변글 조회
    answer = db.query(model).filter(model.qa_type == 1, model.qa_parent == qa_id).first()

    context = {
        "request": request,
        "outlogin": request.state.context["outlogin"],
        "qa": qa,
        "answer": answer,
    }

    return templates.TemplateResponse(f"qa/pc/qa_view.html", context)
