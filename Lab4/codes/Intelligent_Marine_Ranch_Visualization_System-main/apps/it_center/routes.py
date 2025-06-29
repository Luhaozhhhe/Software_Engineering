# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

import os
import json
import requests
import time
from flask import render_template, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from apps.it_center import blueprint

# AI聊天处理函数
@blueprint.route('/index', methods=['GET'])
@login_required
def index():
    return render_template('it_center/index.html',username=current_user.username)

@blueprint.route('/api/chat', methods=['POST'])
def chat():
    # 从请求中获取必要信息
    data = request.json
    user_message = data.get('message', '')
    selected_data = data.get('selectedData', {})
    
    # 构建完整的提示语
    prompt = construct_prompt(user_message, selected_data)
    
    # 检查是否请求流式输出
    stream_mode = data.get('stream', True)
    
    if stream_mode:
        # 返回流式响应
        return Response(stream_with_context(stream_ai_response(prompt)), 
                     content_type='text/event-stream')
    else:
        # 返回完整响应
        response = call_ai_api(prompt)
        return jsonify({
            'success': True,
            'response': response
        })

def construct_prompt(user_message, selected_data):
    """构建发送给AI的完整提示语"""
    context = ""
    
    # 添加水质数据上下文
    if selected_data.get('waterData'):
        water_data = selected_data['waterData']
        context += "\n水质数据上下文:\n"
        
        if 'province' in water_data:
            context += f"省份: {water_data['province']}\n"
        if 'basin' in water_data:
            context += f"流域: {water_data['basin']}\n"
        if 'station' in water_data:
            context += f"监测站点: {water_data['station']}\n"
        if 'parameter' in water_data:
            context += f"监测参数: {water_data['parameter']}\n"
        if 'statistics' in water_data:
            stats = water_data['statistics']
            context += f"统计信息: 平均值={stats.get('mean', 'N/A')}, 最小值={stats.get('min', 'N/A')}, 最大值={stats.get('max', 'N/A')}\n"
    
    # 添加鱼类数据上下文
    if selected_data.get('fishData'):
        fish_data = selected_data['fishData']
        context += "\n鱼类数据上下文:\n"
        
        if 'species' in fish_data:
            context += f"鱼类: {fish_data['species']}\n"
        if 'parameter' in fish_data:
            context += f"参数: {fish_data['parameter']}\n"
        if 'statistics' in fish_data:
            stats = fish_data['statistics']
            context += f"统计信息: 平均值={stats.get('mean', 'N/A')}, 样本数量={stats.get('count', 'N/A')}\n"
    
    # 构建最终提示
    final_prompt = f"{context}\n用户问题: {user_message}\n"
    return final_prompt

def stream_ai_response(prompt):
    """流式调用DeepSeek AI API获取响应"""
    # 使用环境变量获取API密钥
    api_key = os.environ.get('AI_API_KEY', 'sk'+'-d1d534b4562540628dd93f857421e357')
    
    if not api_key:
        yield json.dumps({"type": "error", "content": "错误: 未设置AI API密钥。请联系管理员。"}) + "\n"
        return
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            'model': 'deepseek-chat',
            'messages': [
                {'role': 'system', 'content': '你是一个智能海洋牧场分析助手，擅长分析水质数据和鱼类养殖数据，提供专业的分析和建议。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'stream': True  # 启用流式输出
        }
        
        # 发送流式请求
        response = requests.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers=headers,
            json=payload,
            stream=True  # 使requests支持流式接收
        )
        
        if response.status_code != 200:
            yield json.dumps({"type": "error", "content": f"API调用错误: {response.status_code} - {response.text}"}) + "\n"
            return
        
        # 逐行处理流式响应
        for line in response.iter_lines():
            if line:
                line_text = line.decode('utf-8')
                
                # 跳过空行和"data: [DONE]"行
                if line_text == "" or line_text == "data: [DONE]":
                    continue
                
                # 处理数据行
                if line_text.startswith("data: "):
                    data_str = line_text[6:]  # 去掉 "data: " 前缀
                    try:
                        data = json.loads(data_str)
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                # 发送内容增量
                                yield json.dumps({"type": "content", "content": delta["content"]}) + "\n"
                    except json.JSONDecodeError:
                        continue
        
        # 发送完成信号
        yield json.dumps({"type": "done"}) + "\n"
        
    except Exception as e:
        yield json.dumps({"type": "error", "content": f"发生错误: {str(e)}"}) + "\n"

def call_ai_api(prompt):
    """调用DeepSeek AI API获取完整响应（非流式）"""
    # 使用环境变量获取API密钥
    api_key = os.environ.get('AI_API_KEY', 'sk-181428b7c59744b3a6b39a371e07cbed')
    
    if not api_key:
        return "错误: 未设置AI API密钥。请联系管理员。"
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            'model': 'deepseek-chat',
            'messages': [
                {'role': 'system', 'content': '你是一个智能海洋牧场分析助手，擅长分析水质数据和鱼类养殖数据，提供专业的分析和建议。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7,
            'stream': False
        }
        
        response = requests.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"API调用错误: {response.status_code} - {response.text}"
    
    except Exception as e:
        return f"发生错误: {str(e)}"