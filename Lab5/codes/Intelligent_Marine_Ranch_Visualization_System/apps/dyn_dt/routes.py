# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from apps.dyn_dt import blueprint
from flask import render_template, request, jsonify
import pandas as pd
import numpy as np
import os
import glob
import re
from datetime import datetime, timedelta

import json, csv, io
from flask_login import login_required, current_user
from apps.dyn_dt import blueprint
from flask import render_template, request, redirect, url_for, jsonify, make_response
from apps.dyn_dt.utils import get_model_field_names, get_model_fk_values, name_to_class, user_filter, exclude_auto_gen_fields
from apps import db, config
from apps.dyn_dt.utils import *
from sqlalchemy import and_
from sqlalchemy import Integer, DateTime, String, Text
from datetime import datetime

import urllib.parse

@blueprint.route('/dynamic-dt')
def dynamic_dt():
    context = {
        'routes': config.Config.DYNAMIC_DATATB.keys(),
        'segment': 'dynamic_dt'
    }
    return render_template('dyn_dt/index.html', **context, username=current_user.username)

@blueprint.route('/create_filter/<model_name>', methods=["POST"])
def create_filter(model_name):
    model_name = model_name.lower()
    if request.method == "POST":
        keys = request.form.getlist('key')
        values = request.form.getlist('value')
        
        for key, value in zip(keys, values):
            filter_instance = ModelFilter.query.filter_by(parent=model_name, key=key).first()
            if filter_instance:
                filter_instance.value = value
            else:
                filter_instance = ModelFilter(parent=model_name, key=key, value=value)
            db.session.add(filter_instance)
        
        db.session.commit()
        return redirect(url_for('table_blueprint.model_dt', aPath=model_name))


@blueprint.route('/create_page_items/<model_name>', methods=["POST"])
def create_page_items(model_name):
    model_name = model_name.lower()
    if request.method == 'POST':
        items = request.form.get('items')
        page_items = PageItems.query.filter_by(parent=model_name).first()
        if page_items:
            page_items.items_per_page = items
        else:
            page_items = PageItems(parent=model_name, items_per_page=items)
        db.session.add(page_items)
        db.session.commit()
        return redirect(url_for('table_blueprint.model_dt', aPath=model_name))


@blueprint.route('/create_hide_show_filter/<model_name>', methods=["POST"])
def create_hide_show_filter(model_name):
    model_name = model_name.lower()
    if request.method == "POST":
        data_str = list(request.form.keys())[0]
        data = json.loads(data_str)

        filter_instance = HideShowFilter.query.filter_by(parent=model_name, key=data.get('key')).first()
        if filter_instance:
            filter_instance.value = data.get('value')
        else:
            filter_instance = HideShowFilter(parent=model_name, key=data.get('key'), value=data.get('value'))
        
        db.session.add(filter_instance)
        db.session.commit()

        return jsonify({'message': 'Model updated successfully'})


@blueprint.route('/delete_filter/<model_name>/<int:id>', methods=["GET"])
def delete_filter(model_name, id):
    model_name = model_name.lower()
    filter_instance = ModelFilter.query.filter_by(id=id, parent=model_name).first()
    if filter_instance:
        db.session.delete(filter_instance)
        db.session.commit()
        return redirect(url_for('table_blueprint.model_dt', aPath=model_name))
    return jsonify({'error': 'Filter not found'}), 404


@blueprint.route('/dynamic-dt/<aPath>', methods=['GET', 'POST'])
def model_dt(aPath):
    aModelName = None
    aModelClass = None

    if aPath in config.Config.DYNAMIC_DATATB.keys():
        aModelName = config.Config.DYNAMIC_DATATB[aPath]
        aModelClass = name_to_class(aModelName)

    if not aModelClass:
        return f'ERR: Getting ModelClass for path: {aPath}', 404

    # db_fields = [field.name for field in aModelClass.__table__.columns]
    db_fields = [field.name for field in aModelClass.__table__.columns if not field.foreign_keys]
    fk_fields = get_model_fk_values(aModelClass)
    db_filters = []
    for f in db_fields:
        if f not in fk_fields.keys():
            db_filters.append( f )

    choices_dict = {}
    for column in aModelClass.__table__.columns:
        if isinstance(column.type, db.Enum):
            choices_dict[column.name] = [(choice.name, choice.value) for choice in column.type.enum_class]

    field_names = []
    for field_name in db_fields:
        field = HideShowFilter.query.filter_by(parent=aPath.lower(), key=field_name).first()
        if field:
            field_names.append(field)
        else:
            field = HideShowFilter(parent=aPath.lower(), key=field_name)
            db.session.add(field)
            db.session.commit()

            field_names.append(field)

    filter_string = []
    filter_instance = ModelFilter.query.filter_by(parent=aPath.lower()).all()
    for filter_data in filter_instance:
        if filter_data.key in db_fields:
            filter_string.append(getattr(aModelClass, filter_data.key).like(f"%{filter_data.value}%"))

    order_by = request.args.get('order_by', 'id')
    if order_by not in db_fields:
        order_by = 'id'

    queryset = aModelClass.query.filter(and_(*filter_string)).order_by(order_by)

    # Pagination
    page_items = PageItems.query.filter_by(parent=aPath.lower()).order_by(PageItems.id.desc()).first()
    p_items = 25
    if page_items:
        p_items = page_items.items_per_page

    page = request.args.get('page', 1, type=int)
    queryset = user_filter(request, queryset, db_fields, fk_fields.keys())
    pagination = queryset.paginate(page=page, per_page=p_items, error_out=False)
    items = pagination.items

    # Read-only and field types
    read_only_fields = ('id', 'user_id', 'date_created', 'date_modified', )
    integer_fields = get_model_field_names(aModelClass, Integer)
    date_time_fields = get_model_field_names(aModelClass, DateTime)
    text_fields = get_model_field_names(aModelClass, Text)
    email_fields = []

    # Context
    context = {
        'page_title': f'Dynamic DataTable - {aPath.lower().title()}',
        'link': aPath,
        'field_names': field_names,
        'db_field_names': db_fields,
        'db_filters': db_filters,
        'items': items,
        'pagination': pagination,
        'page_items': p_items,
        'filter_instance': filter_instance,
        'read_only_fields': read_only_fields,
        'integer_fields': integer_fields,
        'date_time_fields': date_time_fields,
        'email_fields': email_fields,
        'text_fields': text_fields,
        'fk_fields_keys': fk_fields.keys(),
        'fk_fields': fk_fields,
        'segment': 'dynamic_dt',
        'choices_dict': choices_dict,
        'exclude_auto_gen_fields': exclude_auto_gen_fields(aModelClass)
    }
    return render_template('dyn_dt/model.html', **context, username=current_user.username)


@blueprint.route('/create/<aPath>', methods=["POST"])
@login_required
def create(aPath):
    aModelClass = None

    if aPath in config.Config.DYNAMIC_DATATB:
        aModelName = config.Config.DYNAMIC_DATATB[aPath]
        aModelClass = name_to_class(aModelName)

    if not aModelClass:
        return ' > ERR: Getting ModelClass for path: ' + aPath

    if request.method == 'POST':
        data = {}
        fk_fields = get_model_fk_values(aModelClass)

        for attribute, value in request.form.items():
            if attribute in fk_fields.keys():
                table_name = None
                for product in fk_fields[attribute]:
                    table_name = product.__class__.__tablename__
                if table_name:
                    model_name = config.Config.DYNAMIC_DATATB[table_name]
                    value = name_to_class(model_name).query.filter_by(id=value).first()

            data[attribute] = value if value else ''

        new_item = aModelClass(**data)
        db.session.add(new_item)
        db.session.commit()

    return redirect(request.referrer) 


@blueprint.route('/delete/<aPath>/<id>', methods=["GET"])
@login_required
def delete(aPath, id):
    aModelClass = None

    if aPath in config.Config.DYNAMIC_DATATB:
        aModelName = config.Config.DYNAMIC_DATATB[aPath]
        aModelClass = name_to_class(aModelName)

    if not aModelClass:
        return ' > ERR: Getting ModelClass for path: ' + aPath
    
    item = aModelClass.query.get(id)
    if item:
        db.session.delete(item)
        db.session.commit()

    return redirect(request.referrer)


@blueprint.route('/update/<aPath>/<int:id>', methods=["POST"])
@login_required
def update(aPath, id):
    aModelClass = None

    if aPath in config.Config.DYNAMIC_DATATB:
        aModelName = config.Config.DYNAMIC_DATATB[aPath]
        aModelClass = name_to_class(aModelName)

    if not aModelClass:
        return ' > ERR: Getting ModelClass for path: ' + aPath

    item = aModelClass.query.get(id)
    if not item:
        return 'Item not found', 404

    fk_fields = get_model_fk_values(aModelClass)

    if request.method == 'POST':
        for attribute, value in request.form.items():
            if hasattr(item, attribute) and getattr(item, attribute, value) is not None:
                if attribute in fk_fields.keys():
                    table_name = None
                    for product in fk_fields[attribute]:
                        table_name = product.__class__.__tablename__
                    if table_name:
                        model_name = config.Config.DYNAMIC_DATATB[table_name]
                        value = name_to_class(model_name).query.filter_by(id=value).first()

                setattr(item, attribute, value)
        
        db.session.commit()

    return redirect(request.referrer)


@blueprint.route('/export/<aPath>', methods=['GET'])
def export_csv(aPath):
    # Check if this is a water quality export request
    province = request.args.get('province')
    basin = request.args.get('basin')
    station = request.args.get('station')
    month = request.args.get('month')
    
    if province and basin and station and month:
        # This is a water quality data export
        csv_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station, month, f"{station}.csv")
        if not os.path.exists(csv_path):
            return 'Data file not found', 404
        
        try:
            # Read the CSV file
            with open(csv_path, 'r', encoding='utf-8') as file:
                content = file.read()
                
            # Prepare response with CSV content
            response = make_response(content)
            response.headers['Content-Type'] = 'text/csv; charset=utf-8'
            
            # 修复中文文件名的问题 - 使用 URL 编码（RFC 5987）
            filename = f"{station}_{month}.csv"
            encoded_filename = urllib.parse.quote(filename)
            response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
            
            return response
        except Exception as e:
            return f'Error reading file: {str(e)}', 500
    
    # If not a water quality export, use the original dynamic table export logic
    aModelName = None
    aModelClass = None

    if aPath in config.Config.DYNAMIC_DATATB:
        aModelName = config.Config.DYNAMIC_DATATB[aPath]
        aModelClass = name_to_class(aModelName)

    if not aModelClass:
        return ' > ERR: Getting ModelClass for path: ' + aPath, 400

    db_field_names = [column.name for column in aModelClass.__table__.columns]
    fk_fields = get_model_fk_values(aModelClass)

    fields = []
    show_fields = HideShowFilter.query.filter_by(value=False, parent=aPath.lower()).all()
    for field in show_fields:
        if field.key in db_field_names:
            fields.append(field.key)
        else:
            print(f"Field {field.key} does not exist in {aModelClass} model.")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)

    # Filtering
    filter_string = {}
    filter_instance = ModelFilter.query.filter_by(parent=aPath.lower()).all()
    for filter_data in filter_instance:
        filter_string[f'{filter_data.key}__icontains'] = filter_data.value

    # Ordering
    order_by = request.args.get('order_by', 'id')
    query = aModelClass.query.filter_by(**filter_string).order_by(order_by)
    items = user_filter(request, query, db_field_names, fk_fields)

    # Write rows to CSV
    for item in items:
        row_data = []
        for field in fields:
            try:
                row_data.append(getattr(item, field))
            except AttributeError:
                row_data.append('')
        writer.writerow(row_data)

    # Prepare response with CSV content
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename="{aPath.lower()}.csv"'

    return response


# Template filter

@blueprint.app_template_filter('getattribute')
def getattribute(value, arg):
    try:
        attr_value = getattr(value, arg)
        
        if isinstance(attr_value, datetime):
            return attr_value.strftime("%Y-%m-%d %H:%M:%S")
        
        return attr_value
    except AttributeError:
        return ''
    

@blueprint.app_template_filter('getenumattribute')
def getenumattribute(value, arg):
    try:
        attr_value = getattr(value, arg)
        return attr_value.value
    except AttributeError:
        return ''


@blueprint.app_template_filter('get')
def get(dict_data, key):
    return dict_data.get(key, [])


# 数据路径配置
FISH_CSV_PATH = os.path.join('Data', 'Fish.csv')
WATER_QUALITY_BY_NAME = os.path.join('Data', 'water_quality_by_name')
WATER_QUALITY_BY_TIME = os.path.join('Data', 'water_quality_by_time')

# 读取鱼类数据
fish_data = pd.read_csv(FISH_CSV_PATH)

@blueprint.route('/index', methods=['GET'])
@login_required
def index():
    return render_template('dyn_dt/index.html')

# ============ 鱼类数据相关 API ============

@blueprint.route('/api/fish/list', methods=['GET'])
@login_required
def get_fish_species_list():
    """获取所有鱼类物种列表"""
    species = fish_data['Species'].unique().tolist()
    return jsonify({
        "success": True,
        "species": species
    })

@blueprint.route('/api/fish/parameters', methods=['GET'])
@login_required
def get_fish_parameters():
    """获取鱼类数据的所有可能参数"""
    # 排除Species列，返回其他列名
    parameters = [col for col in fish_data.columns if col != 'Species']
    return jsonify({
        "success": True,
        "parameters": parameters
    })

@blueprint.route('/api/fish/distribution', methods=['GET'])
@login_required
def get_fish_distribution():
    """获取鱼类参数分布数据"""
    species = request.args.get('species')
    parameter = request.args.get('parameter')
    bins = int(request.args.get('bins', 10))  # 默认10个区间

    if not species or not parameter:
        return jsonify({"success": False, "error": "必须提供species和parameter参数"}), 400

    # 过滤数据
    filtered_data = fish_data[fish_data['Species'] == species][parameter]
    
    if filtered_data.empty:
        return jsonify({"success": False, "error": "没有找到匹配的数据"}), 404

    # 计算基本统计信息
    stats = {
        "count": len(filtered_data),
        "min": filtered_data.min(),
        "max": filtered_data.max(),
        "mean": filtered_data.mean(),
        "median": filtered_data.median(),
        "std": filtered_data.std()
    }

    # 计算区间分布
    min_val, max_val = filtered_data.min(), filtered_data.max()
    bin_range = np.linspace(min_val, max_val, bins + 1)
    labels = [f'{round(bin_range[i], 2)} - {round(bin_range[i + 1], 2)}' for i in range(bins)]
    hist, _ = np.histogram(filtered_data, bins=bin_range)

    response_data = {
        "success": True,
        "species": species,
        "parameter": parameter,
        "statistics": stats,
        "distribution": {
            "labels": labels,
            "values": hist.tolist()
        }
    }
    return jsonify(response_data)

@blueprint.route('/api/fish/comparison', methods=['GET'])
@login_required
def get_fish_comparison():
    """比较不同鱼类的同一参数"""
    parameter = request.args.get('parameter')
    species_list = request.args.getlist('species')  # 可以传入多个species参数

    if not parameter:
        return jsonify({"success": False, "error": "必须提供parameter参数"}), 400
    
    if not species_list:
        # 如果未提供species，默认返回所有鱼类
        species_list = fish_data['Species'].unique().tolist()

    result = []
    for species in species_list:
        species_data = fish_data[fish_data['Species'] == species][parameter]
        if not species_data.empty:
            result.append({
                "species": species,
                "count": len(species_data),
                "min": float(species_data.min()),
                "max": float(species_data.max()),
                "mean": float(species_data.mean()),
                "median": float(species_data.median())
            })

    return jsonify({
        "success": True,
        "parameter": parameter,
        "comparison": result
    })

# ============ 水质数据相关 API ============

@blueprint.route('/api/water/provinces', methods=['GET'])
@login_required
def get_provinces():
    """获取所有省份列表"""
    provinces = []
    for path in glob.glob(os.path.join(WATER_QUALITY_BY_NAME, '*')):
        if os.path.isdir(path):
            province = os.path.basename(path)
            provinces.append(province)
    
    # 按字母顺序排序
    provinces.sort()
    
    return jsonify({
        "success": True,
        "provinces": provinces
    })

@blueprint.route('/api/water/basins', methods=['GET'])
@login_required
def get_basins():
    """获取指定省份的流域列表，如果未指定省份则返回所有流域"""
    province = request.args.get('province')
    
    basins = set()
    if province:
        # 获取指定省份的流域
        province_path = os.path.join(WATER_QUALITY_BY_NAME, province)
        if os.path.isdir(province_path):
            for path in glob.glob(os.path.join(province_path, '*')):
                if os.path.isdir(path):
                    basin = os.path.basename(path)
                    basins.add(basin)
    else:
        # 获取所有流域
        for province_path in glob.glob(os.path.join(WATER_QUALITY_BY_NAME, '*')):
            if os.path.isdir(province_path):
                for path in glob.glob(os.path.join(province_path, '*')):
                    if os.path.isdir(path):
                        basin = os.path.basename(path)
                        basins.add(basin)
    
    # 转为列表并排序
    basins_list = sorted(list(basins))
    
    return jsonify({
        "success": True,
        "province": province,
        "basins": basins_list
    })

@blueprint.route('/api/water/stations', methods=['GET'])
@login_required
def get_stations():
    """获取监测站点列表，可按省份和流域筛选"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    
    stations = []
    
    # 构建基础路径
    base_path = WATER_QUALITY_BY_NAME
    if province:
        base_path = os.path.join(base_path, province)
        if basin:
            base_path = os.path.join(base_path, basin)
    
    # 搜索模式取决于提供的筛选条件
    if province and basin:
        # 指定了省份和流域，获取该流域下的所有站点
        search_pattern = os.path.join(base_path, '*')
        for station_path in glob.glob(search_pattern):
            if os.path.isdir(station_path):
                station = os.path.basename(station_path)
                stations.append({
                    "province": province,
                    "basin": basin,
                    "name": station
                })
    elif province:
        # 只指定了省份，获取该省所有流域下的站点
        for basin_path in glob.glob(os.path.join(base_path, '*')):
            if os.path.isdir(basin_path):
                basin_name = os.path.basename(basin_path)
                for station_path in glob.glob(os.path.join(basin_path, '*')):
                    if os.path.isdir(station_path):
                        station = os.path.basename(station_path)
                        stations.append({
                            "province": province,
                            "basin": basin_name,
                            "name": station
                        })
    else:
        # 没有指定筛选条件，返回所有站点（可能数量很大，考虑添加分页）
        for province_path in glob.glob(os.path.join(base_path, '*')):
            if os.path.isdir(province_path):
                province_name = os.path.basename(province_path)
                for basin_path in glob.glob(os.path.join(province_path, '*')):
                    if os.path.isdir(basin_path):
                        basin_name = os.path.basename(basin_path)
                        for station_path in glob.glob(os.path.join(basin_path, '*')):
                            if os.path.isdir(station_path):
                                station = os.path.basename(station_path)
                                stations.append({
                                    "province": province_name,
                                    "basin": basin_name,
                                    "name": station
                                })
    
    # 排序（先按省份，再按流域，最后按站点名称）
    stations.sort(key=lambda x: (x["province"], x["basin"], x["name"]))
    
    return jsonify({
        "success": True,
        "province": province,
        "basin": basin,
        "total": len(stations),
        "stations": stations
    })

@blueprint.route('/api/water/available_months', methods=['GET'])
@login_required
def get_available_months():
    """获取指定站点的可用月份"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    station = request.args.get('station')
    
    if not all([province, basin, station]):
        return jsonify({"success": False, "error": "必须提供province、basin和station参数"}), 400
    
    # 构建站点路径
    station_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station)
    if not os.path.isdir(station_path):
        return jsonify({"success": False, "error": "指定的站点不存在"}), 404
    
    # 获取可用月份
    months = []
    for month_path in glob.glob(os.path.join(station_path, '*')):
        if os.path.isdir(month_path):
            month = os.path.basename(month_path)
            months.append(month)
    
    # 按时间排序
    months.sort(reverse=True)  # 最新的月份在前
    
    return jsonify({
        "success": True,
        "province": province,
        "basin": basin,
        "station": station,
        "available_months": months
    })

@blueprint.route('/api/water/parameters', methods=['GET'])
@login_required
def get_water_parameters():
    """获取水质数据的参数列表"""
    # 这里返回固定的参数列表
    parameters = [
        {"id": "水温", "name": "水温", "unit": "℃"},
        {"id": "pH", "name": "pH", "unit": "无量纲"},
        {"id": "溶解氧", "name": "溶解氧", "unit": "mg/L"},
        {"id": "电导率", "name": "电导率", "unit": "μS/cm"},
        {"id": "浊度", "name": "浊度", "unit": "NTU"},
        {"id": "高锰酸盐指数", "name": "高锰酸盐指数", "unit": "mg/L"},
        {"id": "氨氮", "name": "氨氮", "unit": "mg/L"},
        {"id": "总磷", "name": "总磷", "unit": "mg/L"},
        {"id": "总氮", "name": "总氮", "unit": "mg/L"},
        {"id": "叶绿素α", "name": "叶绿素α", "unit": "mg/L"},
        {"id": "藻密度", "name": "藻密度", "unit": "cells/L"}
    ]
    
    return jsonify({
        "success": True,
        "parameters": parameters
    })

@blueprint.route('/api/water/station_data', methods=['GET'])
@login_required
def get_station_data():
    """获取指定站点的水质数据"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    station = request.args.get('station')
    year_month = request.args.get('month')  # 格式: YYYY-MM
    parameter = request.args.get('parameter')
    start_date = request.args.get('start_date')  # 格式: MM-DD
    end_date = request.args.get('end_date')  # 格式: MM-DD
    
    if not all([province, basin, station, year_month]):
        return jsonify({"success": False, "error": "必须提供province、basin、station和month参数"}), 400
    
    # 构建CSV文件路径
    csv_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station, year_month, f"{station}.csv")
    if not os.path.exists(csv_path):
        return jsonify({"success": False, "error": "指定的数据文件不存在"}), 404
    
    try:
        # 读取CSV数据
        df = pd.read_csv(csv_path)
        
        # 处理日期过滤
        if start_date or end_date:
            # 从监测时间列中提取日期部分（前5个字符，例如 "04-01"）
            df['日期'] = df['监测时间'].apply(lambda x: str(x)[:5] if pd.notna(x) and str(x) != '*' else None)
            
            if start_date:
                df = df[df['日期'] >= start_date]
            if end_date:
                df = df[df['日期'] <= end_date]
            
            # 删除临时列
            df = df.drop('日期', axis=1)
        
        # 处理参数过滤
        if parameter:
            # 仅保留参数相关列和基础信息列
            param_col = next((col for col in df.columns if col.startswith(parameter)), None)
            if param_col:
                # 保留基础列和指定参数列
                base_cols = ['省份', '流域', '断面名称', '监测时间', '水质类别', '站点情况']
                selected_cols = base_cols + [param_col]
                df = df[selected_cols]
        
        # 去除无效行（完全的null、--或*行）
        df = df[~df.iloc[:, 5:].apply(lambda row: all(val in ['--', '*', np.nan] or pd.isna(val) for val in row), axis=1)]
        
        # 转换为记录列表
        records = df.to_dict('records')
        
        # 提取唯一的日期和时间段
        timestamps = df['监测时间'].dropna().unique().tolist()
        timestamps = [ts for ts in timestamps if ts != '*']
        
        dates = sorted(list(set([ts.split()[0] if ' ' in ts else ts for ts in timestamps])))
        time_periods = sorted(list(set([ts.split()[1] if ' ' in ts else '' for ts in timestamps if ' ' in ts])))
        
        return jsonify({
            "success": True,
            "province": province,
            "basin": basin,
            "station": station,
            "month": year_month,
            "parameter": parameter,
            "data": records,
            "dates": dates,
            "time_periods": time_periods,
            "total_records": len(records)
        })
    
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"读取数据时出错: {str(e)}"
        }), 500

@blueprint.route('/api/water/parameter_trend', methods=['GET'])
@login_required
def get_parameter_trend():
    """获取指定站点和参数随时间的变化趋势"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    station = request.args.get('station')
    year_month = request.args.get('month')  # 格式: YYYY-MM
    parameter = request.args.get('parameter')
    
    if not all([province, basin, station, year_month, parameter]):
        return jsonify({"success": False, "error": "必须提供province、basin、station、month和parameter参数"}), 400
    
    # 构建CSV文件路径
    csv_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station, year_month, f"{station}.csv")
    if not os.path.exists(csv_path):
        return jsonify({"success": False, "error": "指定的数据文件不存在"}), 404
    
    try:
        # 读取CSV数据
        df = pd.read_csv(csv_path)
        
        # 找到对应参数的列
        param_col = next((col for col in df.columns if col.startswith(parameter)), None)
        if not param_col:
            return jsonify({"success": False, "error": f"未找到参数 '{parameter}' 的数据列"}), 404
        
        # 提取监测时间和参数值
        trend_data = []
        for _, row in df.iterrows():
            time_str = row['监测时间']
            param_value = row[param_col]
            
            # 跳过无效数据
            if pd.isna(time_str) or time_str == '*' or pd.isna(param_value) or param_value in ['--', '*']:
                continue
            
            # 尝试将参数值转为数值
            try:
                value = float(param_value)
            except:
                continue
            
            # 将'04-01 08:00'转换为完整日期时间格式
            try:
                # 假设年份为year_month的前4位
                year = year_month[:4]
                full_date_str = f"{year}-{time_str}"
                # 构建ISO格式日期时间
                if ' ' in time_str:
                    date_part, time_part = time_str.split(' ')
                    month, day = date_part.split('-')
                    full_date_str = f"{year}-{month}-{day} {time_part}"
                    dt = datetime.strptime(full_date_str, '%Y-%m-%d %H:%M')
                else:
                    month, day = time_str.split('-')
                    full_date_str = f"{year}-{month}-{day}"
                    dt = datetime.strptime(full_date_str, '%Y-%m-%d')
                
                trend_data.append({
                    "timestamp": dt.isoformat(),
                    "date": f"{year}-{time_str.split(' ')[0] if ' ' in time_str else time_str}",
                    "time": time_str.split(' ')[1] if ' ' in time_str else None,
                    "value": value,
                    "category": row['水质类别'] if pd.notna(row['水质类别']) else None
                })
            except Exception as e:
                print(f"日期解析错误: {time_str}, 错误: {str(e)}")
                continue
        
        # 按时间戳排序
        trend_data.sort(key=lambda x: x["timestamp"])
        
        # 计算统计信息
        values = [item["value"] for item in trend_data]
        stats = {}
        if values:
            stats = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "std": np.std(values)
            }
        
        # 提取水质类别统计
        categories = {}
        for item in trend_data:
            cat = item["category"]
            if cat and cat != '*':
                categories[cat] = categories.get(cat, 0) + 1
        
        return jsonify({
            "success": True,
            "province": province,
            "basin": basin,
            "station": station,
            "month": year_month,
            "parameter": parameter,
            "unit": param_col.split('(')[1].split(')')[0] if '(' in param_col else "",
            "trend": trend_data,
            "statistics": stats,
            "categories": categories
        })
    
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"生成趋势数据时出错: {str(e)}"
        }), 500

@blueprint.route('/api/water/station_statistics', methods=['GET'])
@login_required
def get_station_statistics():
    """获取站点的水质参数统计信息"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    station = request.args.get('station')
    year_month = request.args.get('month')  # 格式: YYYY-MM
    
    if not all([province, basin, station, year_month]):
        return jsonify({"success": False, "error": "必须提供province、basin、station和month参数"}), 400
    
    # 构建CSV文件路径
    csv_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station, year_month, f"{station}.csv")
    if not os.path.exists(csv_path):
        return jsonify({"success": False, "error": "指定的数据文件不存在"}), 404
    
    try:
        # 读取CSV数据
        df = pd.read_csv(csv_path)
        
        # 获取参数列（除了基本信息列）
        param_cols = df.columns[5:-1]  # 排除前5列和最后一列
        
        # 计算每个参数的统计信息
        param_stats = []
        for col in param_cols:
            # 提取参数名称和单位
            param_name = col.split('(')[0] if '(' in col else col
            param_unit = col.split('(')[1].split(')')[0] if '(' in col else ""
            
            # 过滤有效值
            values = []
            for val in df[col]:
                if pd.notna(val) and val != '--' and val != '*':
                    try:
                        values.append(float(val))
                    except:
                        pass
            
            # 计算统计值
            if values:
                stats = {
                    "name": param_name,
                    "unit": param_unit,
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                    "std": np.std(values)
                }
                param_stats.append(stats)
        
        # 统计水质类别
        categories = {}
        for cat in df['水质类别'].dropna().unique():
            if cat != '*':
                count = len(df[df['水质类别'] == cat])
                categories[cat] = count
        
        # 统计站点情况
        status = {}
        for st in df['站点情况'].dropna().unique():
            if st != '*':
                count = len(df[df['站点情况'] == st])
                status[st] = count
        
        return jsonify({
            "success": True,
            "province": province,
            "basin": basin,
            "station": station,
            "month": year_month,
            "total_records": len(df),
            "parameter_statistics": param_stats,
            "water_quality_categories": categories,
            "station_status": status
        })
    
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"计算统计信息时出错: {str(e)}"
        }), 500

@blueprint.route('/api/water/compare_stations', methods=['GET'])
@login_required
def compare_stations():
    """比较多个站点的同一参数"""
    parameter = request.args.get('parameter')
    year_month = request.args.get('month')  # 格式: YYYY-MM
    date = request.args.get('date')  # 可选，格式: MM-DD
    
    # 获取多个站点信息
    stations = request.args.getlist('station')  # 格式: province|basin|station
    
    if not parameter or not year_month or not stations:
        return jsonify({"success": False, "error": "必须提供parameter、month和至少一个station参数"}), 400
    
    comparison_data = []
    
    for station_str in stations:
        parts = station_str.split('|')
        if len(parts) != 3:
            continue
            
        province, basin, station = parts
        
        # 构建CSV文件路径
        csv_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station, year_month, f"{station}.csv")
        if not os.path.exists(csv_path):
            continue
        
        try:
            # 读取CSV数据
            df = pd.read_csv(csv_path)
            
            # 找到对应参数的列
            param_col = next((col for col in df.columns if col.startswith(parameter)), None)
            if not param_col:
                continue
            
            # 如果指定了日期，过滤数据
            if date:
                df = df[df['监测时间'].apply(lambda x: str(x).startswith(date) if pd.notna(x) and str(x) != '*' else False)]
            
            # 提取有效值
            values = []
            for val in df[param_col]:
                if pd.notna(val) and val != '--' and val != '*':
                    try:
                        values.append(float(val))
                    except:
                        pass
            
            # 计算统计值
            if values:
                stats = {
                    "province": province,
                    "basin": basin,
                    "station": station,
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                    "std": np.std(values)
                }
                comparison_data.append(stats)
        
        except Exception as e:
            print(f"处理站点 {station} 时出错: {str(e)}")
    
    # 按平均值排序
    comparison_data.sort(key=lambda x: x["mean"], reverse=True)
    
    return jsonify({
        "success": True,
        "parameter": parameter,
        "month": year_month,
        "date": date,
        "comparison": comparison_data
    })

@blueprint.route('/api/water/basin_overview', methods=['GET'])
@login_required
def get_basin_overview():
    """获取指定流域的水质概览"""
    province = request.args.get('province')
    basin = request.args.get('basin')
    year_month = request.args.get('month')  # 格式: YYYY-MM
    parameter = request.args.get('parameter')  # 可选
    
    if not all([province, basin, year_month]):
        return jsonify({"success": False, "error": "必须提供province、basin和month参数"}), 400
    
    # 构建流域路径
    basin_path = os.path.join(WATER_QUALITY_BY_NAME, province, basin)
    if not os.path.isdir(basin_path):
        return jsonify({"success": False, "error": "指定的流域不存在"}), 404
    
    basin_data = []
    
    # 遍历流域下的所有站点
    for station_path in glob.glob(os.path.join(basin_path, '*')):
        if not os.path.isdir(station_path):
            continue
            
        station = os.path.basename(station_path)
        
        # 检查是否有指定月份的数据
        month_path = os.path.join(station_path, year_month)
        if not os.path.isdir(month_path):
            continue
            
        # 构建CSV文件路径
        csv_path = os.path.join(month_path, f"{station}.csv")
        if not os.path.exists(csv_path):
            continue
        
        try:
            # 读取CSV数据
            df = pd.read_csv(csv_path)
            
            # 如果指定了参数，只关注该参数
            if parameter:
                param_col = next((col for col in df.columns if col.startswith(parameter)), None)
                if not param_col:
                    continue
                
                # 提取有效值
                values = []
                for val in df[param_col]:
                    if pd.notna(val) and val != '--' and val != '*':
                        try:
                            values.append(float(val))
                        except:
                            pass
                
                if values:
                    stats = {
                        "station": station,
                        "parameter": parameter,
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "mean": sum(values) / len(values),
                        "std": np.std(values)
                    }
                    basin_data.append(stats)
            else:
                # 统计水质类别
                categories = {}
                for cat in df['水质类别'].dropna().unique():
                    if cat != '*':
                        count = len(df[df['水质类别'] == cat])
                        categories[cat] = count
                
                # 找出主要水质类别
                main_category = max(categories.items(), key=lambda x: x[1])[0] if categories else None
                
                station_info = {
                    "station": station,
                    "records": len(df),
                    "water_quality_categories": categories,
                    "main_category": main_category
                }
                basin_data.append(station_info)
                
        except Exception as e:
            print(f"处理站点 {station} 时出错: {str(e)}")
    
    # 排序
    if parameter:
        basin_data.sort(key=lambda x: x["mean"], reverse=True)
    else:
        basin_data.sort(key=lambda x: x["station"])
    
    return jsonify({
        "success": True,
        "province": province,
        "basin": basin,
        "month": year_month,
        "parameter": parameter,
        "stations_count": len(basin_data),
        "data": basin_data
    })

@blueprint.route('/api/water/search', methods=['GET'])
@login_required
def search_water_stations():
    """搜索水质监测站点"""
    query = request.args.get('q')
    if not query or len(query) < 2:
        return jsonify({"success": False, "error": "搜索关键字必须至少包含2个字符"}), 400
    
    results = []
    
    # 遍历所有省份、流域和站点
    for province_path in glob.glob(os.path.join(WATER_QUALITY_BY_NAME, '*')):
        if not os.path.isdir(province_path):
            continue
            
        province = os.path.basename(province_path)
        
        for basin_path in glob.glob(os.path.join(province_path, '*')):
            if not os.path.isdir(basin_path):
                continue
                
            basin = os.path.basename(basin_path)
            
            for station_path in glob.glob(os.path.join(basin_path, '*')):
                if not os.path.isdir(station_path):
                    continue
                    
                station = os.path.basename(station_path)
                
                # 检查是否匹配搜索关键字
                if (query.lower() in province.lower() or 
                    query.lower() in basin.lower() or 
                    query.lower() in station.lower()):
                    
                    # 获取可用月份
                    months = []
                    for month_path in glob.glob(os.path.join(station_path, '*')):
                        if os.path.isdir(month_path):
                            month = os.path.basename(month_path)
                            months.append(month)
                    
                    months.sort(reverse=True)
                    
                    results.append({
                        "province": province,
                        "basin": basin,
                        "station": station,
                        "available_months": months
                    })
    
    # 排序结果
    results.sort(key=lambda x: (x["province"], x["basin"], x["station"]))
    
    return jsonify({
        "success": True,
        "query": query,
        "total": len(results),
        "results": results
    })

@blueprint.route('/api/water/upload', methods=['POST'])
@login_required
def upload_water_data():
    """Upload water quality data in CSV format"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有上传文件"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "未选择文件"}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({"success": False, "error": "只支持CSV文件格式"}), 400
    
    # Get form data
    province = request.form.get('province')
    basin = request.form.get('basin')
    station = request.form.get('station')
    month = request.form.get('month')
    
    if not all([province, basin, station, month]):
        return jsonify({"success": False, "error": "必须提供province、basin、station和month参数"}), 400
    
    # Check if the folder structure exists, create if not
    station_folder = os.path.join(WATER_QUALITY_BY_NAME, province, basin, station)
    if not os.path.exists(station_folder):
        os.makedirs(station_folder, exist_ok=True)
    
    month_folder = os.path.join(station_folder, month)
    if not os.path.exists(month_folder):
        os.makedirs(month_folder, exist_ok=True)
    
    # Target path for saving the file
    target_path = os.path.join(month_folder, f"{station}.csv")
    
    try:
        # Save the file temporarily to validate format
        temp_file_path = os.path.join(month_folder, "temp.csv")
        file.save(temp_file_path)
        
        # Validate CSV format
        try:
            df = pd.read_csv(temp_file_path)
            
            # Check if required columns exist
            required_columns = ['省份', '流域', '断面名称', '监测时间', '水质类别']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                os.remove(temp_file_path)
                return jsonify({
                    "success": False, 
                    "error": f"CSV文件缺少必要的列: {', '.join(missing_columns)}"
                }), 400
            
            # Rename the file
            os.rename(temp_file_path, target_path)
            
            # Also save to time-based structure
            time_based_folder = os.path.join(WATER_QUALITY_BY_TIME, month)
            if not os.path.exists(time_based_folder):
                os.makedirs(time_based_folder, exist_ok=True)
            
            time_based_path = os.path.join(time_based_folder, f"{province}_{basin}_{station}.csv")
            df.to_csv(time_based_path, index=False)
            
            return jsonify({
                "success": True,
                "message": "数据上传成功",
                "province": province,
                "basin": basin,
                "station": station,
                "month": month,
                "record_count": len(df)
            })
            
        except Exception as e:
            # Remove temp file if validation fails
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return jsonify({"success": False, "error": f"CSV文件格式无效: {str(e)}"}), 400
    
    except Exception as e:
        return jsonify({"success": False, "error": f"上传文件时发生错误: {str(e)}"}), 500