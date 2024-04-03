from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime, timedelta
import os
import re
import requests
from werkzeug.utils import secure_filename
from pyzbar.pyzbar import decode
import json
from PIL import Image
import numpy as np
import cv2
import qrcode
#os.chdir('/app')


UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.static_folder = 'uploads'

# 存储用户上传的图片信息
uploaded_images = []


usage_count_file = 'usage_count.txt'


# 读取功能使用次数
def read_usage_count():
    try:
        with open(usage_count_file, 'r') as file:
            return int(file.read())
    except FileNotFoundError:
        return 0


# 保存功能使用次数
def save_usage_count(count):
    with open(usage_count_file, 'w') as file:
        file.write(str(count))


def check_file_in_folder(title):
    files = os.listdir('uploads')
    if (title + '.txt') in files:
        return True
    else:
        return False


# 检查图片是否是二维码
def is_qr_code(image_path):
    count = read_usage_count()
    count += 1
    save_usage_count(count)
    pil_image = Image.open(image_path)
    # 将PIL图像转换为NumPy数组
    image_np = np.array(pil_image)
    # 将NumPy数组传递给OpenCV
    try:
        image = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    # 转换为灰度图
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    except:
        gray_image= image_np
    # 解码图片中的二维码
    decocdeQR = decode(gray_image)
    if not decocdeQR:
        return 0
    else:
        qrvalue = ''
        for obj in decocdeQR:
            # 提取二维码的位置和数据
            x, y, w, h = obj.rect
            # 提取二维码的图像
            qr_code = gray_image[y:y + h, x:x + w]
            # 对二维码图像进行二值化处理
            _, qr_code_bin = cv2.threshold(qr_code, 128, 255, cv2.THRESH_BINARY)
            # 打印二维码数据
            qrvalue = obj.data.decode('utf-8')
        print(qrvalue)
        try:
            parts = qrvalue.split('|')
            info_part = parts[1]

            # 解析信息部分为字典
            info_dict = {}
            for item in info_part.split('&'):
                key, value = item.split('=')
                info_dict[key] = value
            current_time = datetime.now()
            current_time += timedelta(minutes=60)
            # 格式化为所需的字符串格式
            custom_timestamp = current_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # 去除毫秒的后三位
            # 匹配时间戳的正则表达式模式
            timestamp_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}'
            # 替换时间戳
            replaced_string = re.sub(timestamp_pattern, custom_timestamp, qrvalue)
            print(replaced_string)
            img = qrcode.make(replaced_string)
            # 保存图像
            img.save(image_path)
            # 显示二维码
        except:
            print("不是合法二维码")
            return 2
    return 1


def get_txt_files():
    # 获取文件夹中的所有txt文件名
    txt_files = [file[:-4] for file in os.listdir('Accounts') if file.endswith('.txt')]
    return txt_files


# 主页
@app.route('/')
def index():
    try:
        usage_count = read_usage_count()
    except:
        usage_count = 0
    upload_folder = app.config['UPLOAD_FOLDER']
    image_files = os.listdir(upload_folder)
    images = []
    images_exd = []
    now = datetime.now()

    # 创建包含文件名和创建时间的元组列表
    file_time_tuples = []
    for image_file in image_files:
        if image_file[-3:] == 'txt':
            continue
        try:
            creation_time = os.path.getctime(os.path.join(upload_folder, image_file))
            file_time_tuples.append((image_file, creation_time))
        except OSError:
            # 如果无法获取文件创建时间，跳过该文件
            continue

    # 按照创建时间对文件列表进行排序
    sorted_file_time_tuples = sorted(file_time_tuples, key=lambda x: x[1], reverse=True)
    current_time = float(datetime.now().timestamp())
    # 根据排序后的文件列表生成图片信息字典
    for image_file, creation_time in sorted_file_time_tuples:
        try:
            t_difference = current_time - creation_time
            # 如果文件创建时间超过 24 小时（86400 秒），则删除文件
            if t_difference > 86400:
                os.remove('uploads/' + image_file)
                os.remove('uploads/' + image_file[:image_file.rfind('.')] + '.txt')
                continue
        except:
            pass
        try:
            title, expiry_time_str = image_file.split('--')
            expiry_time = datetime.strptime(expiry_time_str.split('.')[0], '%Y-%m-%d-%H-%M-%S')
            expired = expiry_time < now
            if expired:
                images_exd.append({'filename': image_file, 'title': title,
                               'creation_time': datetime.fromtimestamp(creation_time).strftime('%Y-%m-%d %H:%M:%S'),
                               'expiry_time': expiry_time.strftime('%Y-%m-%d-%H-%M-%S'), 'expired': expired})
            else:
                images.append({'filename':image_file,'title': title, 'creation_time': datetime.fromtimestamp(creation_time).strftime('%Y-%m-%d %H:%M:%S'), 'expiry_time': expiry_time.strftime('%Y-%m-%d-%H-%M-%S'), 'expired': expired})
        except ValueError:
            # 如果无法解析过期时间，跳过该文件
            continue
    images+=(images_exd)
    return render_template('index.html', images=images,usage_count=usage_count)


# 上传图片
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files['file']
        title = request.form['title']
        expiry_minutes = int(request.form['expiry_time'])
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            expiry_time = datetime.now() + timedelta(minutes=expiry_minutes)
            new_filename = f"{title}--{expiry_time.strftime('%Y-%m-%d-%H-%M-%S')}.{filename.split('.')[-1]}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
            qrresult = is_qr_code(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
            if qrresult  == 0:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                return render_template('upload.html', error_message="上传的图片没有二维码，或者识别不到，尝试拍的清楚一些吧")
            elif qrresult == 2:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                return render_template('upload.html',
                                       error_message="上传的图片不是合法的二维码")
            return redirect(url_for('index'))
    return render_template('upload.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True)
