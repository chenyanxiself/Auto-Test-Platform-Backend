#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2020/6/11 5:21 下午
# @Author  : yxChen

import logging
from fastapi import APIRouter, Body, Depends
from util.jwt_util import create_access_token, auth_token
from models.request_model.user_reqm import TokenUser
from consts.log_name import API_LOGIN
from models.response_model.base_resm import BaseRes
from models.request_model.user_reqm import LoginUser, AddUser, UpdatePassword, UpdateUserInfo
from util.encrypt_util import verify_password, get_password_hash
from models.db_model.model import *
from models.db_model.db import Db
from datetime import datetime
from typing import List
import traceback

router = APIRouter()
logger = logging.getLogger(API_LOGIN)


@router.post('/login/', response_model=BaseRes)
async def login(login_user: LoginUser) -> BaseRes:
    user_list = Db.select_by_condition(SysUser, [SysUser.name == login_user.user_name, SysUser.is_delete == '2'])
    if (len(user_list)) == 0:
        return BaseRes(status=0, error='用户名或密码错误')
    else:
        user: SysUser = user_list[0]
        if verify_password(login_user.password, user.password):
            token_data = {'id': user.id, 'cname': user.cname}
            token = create_access_token(data=token_data)
            data = {'token': token, 'type': 'Bearer'}
            return BaseRes(data=data)
        else:
            return BaseRes(status=0, error='用户名或密码错误')


@router.post('/getCurrentUser/', response_model=BaseRes)
async def get_current_user(token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    current_user: SysUser = Db.select_by_primary_key(SysUser, token_user.user_id)
    data = {
        'id': current_user.id,
        'name': current_user.name,
        'cname': current_user.cname,
        'email': current_user.email,
        'phone': current_user.phone
    }
    return BaseRes(data=data)


@router.post('/getAllUser/', dependencies=[Depends(auth_token)], response_model=BaseRes)
async def get_all_user() -> BaseRes:
    try:
        user_list: List[SysUser] = Db.select_by_condition(SysUser, [SysUser.is_delete == '2'])
        res_user_list = []
        for user in user_list:
            res_user_list.append({
                'id': user.id,
                'cname': user.cname,
                # 'name':user.name,
                # 'email':user.email,
                # 'phone':user.phone
            })
        data = {'userList': res_user_list}
        return BaseRes(data=data)
    except Exception as e:
        logger.error(traceback.format_exc())
        return BaseRes(status=0, error=str(e))


@router.post('/createUser/', response_model=BaseRes)
async def add_user(user: AddUser, token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    hash_paaword = get_password_hash(user.password)
    session = Db.get_session()
    try:
        new_user = SysUser(
            name=user.user_name,
            password=hash_paaword,
            cname=user.user_cname,
            email=user.email,
            phone=user.phone,
            creator=token_user.user_id,
            create_time=datetime.now()
        )
        session.add(new_user)
        session.commit()
        for role_id in user.role_ids:
            session.add(SysUserRole(
                user_id=new_user.id,
                role_id=role_id,
                creator=token_user.user_id,
                create_time=datetime.now()
            ))
        session.commit()
        return BaseRes(data='success')
    except Exception as e:
        session.rollback()
        logger.error(traceback.format_exc())
        return BaseRes(status=0, error=e)


@router.post('/updatePassword', response_model=BaseRes)
async def update_password(data: UpdatePassword, token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    user: SysUser = Db.select_by_primary_key(SysUser, token_user.user_id)
    if verify_password(data.old_password, user.password):
        try:
            hash_paaword = get_password_hash(data.new_password)
            Db.update_by_condition(
                SysUser,
                [SysUser.id == token_user.user_id],
                {
                    SysUser.password: hash_paaword,
                    SysUser.updator: token_user.user_id,
                    SysUser.update_time: datetime.now()
                })
            return BaseRes()
        except Exception as e:
            logger.error(e)
            return BaseRes(status=0, error='更新密码失败')
    else:
        return BaseRes(status=0, error='密码错误')


@router.post('/updateUserInfo', response_model=BaseRes)
async def update_user_info(data: UpdateUserInfo, token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    session = Db.get_session()
    try:
        session.query(SysUser).filter(*[
            SysUser.id == data.user_id,
            SysUser.is_delete == 2
        ]).update({
            SysUser.cname: data.user_cname,
            SysUser.email: data.email,
            SysUser.phone: data.phone,
            SysUser.updator: token_user.user_id,
            SysUser.update_time: datetime.now()
        })
        if data.role_ids is not None:
            session.query(SysUserRole).filter(*[
                SysUserRole.user_id == data.user_id,
                SysUserRole.role_id.notin_(data.role_ids)
            ]).update({
                SysUserRole.is_delete: 1,
                SysUserRole.updator: token_user.user_id,
                SysUserRole.update_time: datetime.now()
            }, synchronize_session=False)
            session.query(SysUserRole).filter(*[
                SysUserRole.user_id == data.user_id,
                SysUserRole.role_id.in_(data.role_ids)
            ]).update({
                SysUserRole.is_delete: 2,
                SysUserRole.updator: token_user.user_id,
                SysUserRole.update_time: datetime.now()
            }, synchronize_session=False)
            temps: List[SysUserRole] = session.query(SysUserRole).filter(*[
                SysUserRole.user_id == data.user_id,
                SysUserRole.role_id.in_(data.role_ids)
            ]).all()
            already_role_ids = set([x.role_id for x in temps])
            gap_role_ids = set(data.role_ids) - already_role_ids
            for i in gap_role_ids:
                session.add(SysUserRole(
                    user_id=data.user_id,
                    role_id=i
                ))
        session.commit()
        return BaseRes()
    except Exception as e:
        session.rollback()
        logger.error(traceback.format_exc())
        return BaseRes(status=0, error=str(e))


@router.post('/deleteUser/', response_model=BaseRes)
async def delete_user(user_id: int = Body(...), token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    session = Db.get_session()
    try:
        session.query(SysUser).filter(*[
            SysUser.id == user_id,
            SysUser.is_delete == 2
        ]).update({
            SysUser.is_delete: 1,
            SysUser.updator: token_user.user_id,
            SysUser.update_time: datetime.now()
        })
        session.commit()
        return BaseRes(data='success')
    except Exception as e:
        session.rollback()
        logger.error(traceback.format_exc())
        return BaseRes(status=0, error=e)


@router.get('/getMenuAuth/', response_model=BaseRes)
async def get_current_user(token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    session = Db.get_session()
    try:
        user_role_list: List[SysUserRole] = session.query(SysUserRole).filter(*[
            SysUserRole.is_delete == 2,
            SysUserRole.user_id == token_user.user_id
        ]).all()
        if len(user_role_list) == 0:
            return BaseRes(data=[])
        user_role_id_list = [x.id for x in user_role_list]
        menu_map_list: List[SysRoleMenu] = session.query(SysRoleMenu).filter(*[
            SysRoleMenu.is_delete == 2,
            SysRoleMenu.role_id.in_(user_role_id_list)
        ]).all()
        menus_ids = set()
        for menu_map in menu_map_list:
            menus_ids.add(menu_map.id)
        menus: List[SysMenu] = session.query(SysMenu).filter(*[
            SysMenu.is_delete == 2,
            SysMenu.id.in_(menus_ids)
        ]).all()
        return_value = []
        for m in menus:
            return_value.append({
                'id': m.id,
                'name': m.name,
                'regExp': m.menu_reg,
                'path': m.menu_path,
                'parentId': m.parent_id,
                'icon': m.icon
            })
        return BaseRes(data=return_value)
    except Exception as e:
        logger.warning(traceback.format_exc())
        return BaseRes(status=0, error=str(e))


@router.get('/getAllRoleList/', response_model=BaseRes)
async def get_current_user(token_user: TokenUser = Depends(auth_token)) -> BaseRes:
    session = Db.get_session()
    try:
        role_list: List[SysRole] = session.query(SysRole).filter(*[
            SysRole.is_delete == 2
        ]).all()
        return BaseRes(data=role_list)
    except Exception as e:
        logger.warning(traceback.format_exc())
        return BaseRes(status=0, error=str(e))
