from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
import os
import socket
import requests

app = Flask(__name__)
app.secret_key = os.urandom(24)
socketio = SocketIO(app, async_mode='gevent')

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='1234',
        database='bsm18',
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8mb4'
    )


# Yerel IP adresini dinamik olarak almak için fonksiyon
def get_local_ip():
    try:
        # Bir socket oluştur ve Google DNS'e bağlan (bağlantı gerçekleşmez, sadece IP alınır)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        return "127.0.0.1"  # Eğer IP alınamazsa localhost döner





@app.route('/')
def home():
    if 'user_id' in session:
        return render_template('chat.html')
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    kullanici_adi = data.get('kullanici_adi')
    email = data.get('email')
    sifre = data.get('sifre')

    hashed_sifre = generate_password_hash(sifre)
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "INSERT INTO kullanici (kullanici_adi, email, sifre_hash) VALUES (%s, %s, %s)"
                cursor.execute(sql, (kullanici_adi, email, hashed_sifre))
                connection.commit()
                return jsonify({'message': 'Kayıt başarılı!'}), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Kayıt sırasında bir hata oluştu!'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    sifre = data.get('sifre')

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM kullanici WHERE email = %s"
                cursor.execute(sql, (email,))
                user = cursor.fetchone()

                if user and check_password_hash(user['sifre_hash'], sifre):
                    session['user_id'] = user['kullanici_id']
                    session['kullanici_adi'] = user['kullanici_adi']
                    return jsonify({'message': 'Giriş başarılı!', 'user': user}), 200
                else:
                    return jsonify({'error': 'Giriş bilgileriniz hatalı. Lütfen tekrar deneyin.'}), 401
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Giriş sırasında bir hata oluştu!'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('kullanici_adi', None)
    return jsonify({'message': 'Çıkış başarılı!'}), 200

@app.route('/api/gruplar', methods=['GET'])
def get_gruplar():
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "SELECT grup_id, grup_adi FROM grup"
                cursor.execute(sql)
                gruplar = cursor.fetchall()
                return jsonify(gruplar), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Gruplar alınırken bir hata oluştu!'}), 500

@app.route('/api/grup_olustur', methods=['POST'])
def grup_olustur():
    data = request.json
    grup_adi = data.get('grup_adi')
    olusturan_id = session.get('user_id')

    if not grup_adi:
        return jsonify({'error': 'Grup adı boş olamaz!'}), 400

    if not olusturan_id:
        return jsonify({'error': 'Oturum açık değil!'}), 401

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "INSERT INTO grup (grup_adi, olusturan_id) VALUES (%s, %s)"
                cursor.execute(sql, (grup_adi, olusturan_id))
                grup_id = cursor.lastrowid

                sql = "INSERT INTO grup_uyeleri (grup_id, kullanici_id) VALUES (%s, %s)"
                cursor.execute(sql, (grup_id, olusturan_id))
                connection.commit()

                return jsonify({'message': 'Grup başarıyla oluşturuldu!', 'grup_id': grup_id}), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Grup oluşturulurken bir hata oluştu!'}), 500

@app.route('/api/grup_mesajlar', methods=['GET'])
def get_grup_mesajlar():
    grup_id = request.args.get('grup_id')
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = """
                    SELECT m.*, k.kullanici_adi as gonderen_adi
                    FROM mesaj m
                    JOIN kullanici k ON m.gonderen_id = k.kullanici_id
                    WHERE m.grup_id = %s
                    ORDER BY m.tarih ASC
                """
                cursor.execute(sql, (grup_id,))
                mesajlar = cursor.fetchall()
                return jsonify(mesajlar), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Grup mesajları alınırken bir hata oluştu!'}), 500

@app.route('/api/tum_mesajlar', methods=['GET'])
def get_tum_mesajlar():
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql_bireysel = """
                    SELECT m.*, k.kullanici_adi as gonderen_adi
                    FROM mesaj m
                    JOIN kullanici k ON m.gonderen_id = k.kullanici_id
                    WHERE (m.gonderen_id = %s OR m.alici_id = %s) AND m.grup_id IS NULL
                    ORDER BY m.tarih ASC
                """
                cursor.execute(sql_bireysel, (session['user_id'], session['user_id']))
                bireysel_mesajlar = cursor.fetchall()

                sql_grup = """
                    SELECT m.*, k.kullanici_adi as gonderen_adi
                    FROM mesaj m
                    JOIN kullanici k ON m.gonderen_id = k.kullanici_id
                    WHERE m.grup_id IN (SELECT grup_id FROM grup_uyeleri WHERE kullanici_id = %s)
                    ORDER BY m.tarih ASC
                """
                cursor.execute(sql_grup, (session['user_id'],))
                grup_mesajlar = cursor.fetchall()

                tum_mesajlar = bireysel_mesajlar + grup_mesajlar
                return jsonify(tum_mesajlar), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Mesajlar alınırken bir hata oluştu!'}), 500

@app.route('/api/mesajlar', methods=['GET'])
def get_mesajlar():
    alici_id = request.args.get('alici_id')
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = """
                    SELECT m.*, k.kullanici_adi as gonderen_adi
                    FROM mesaj m
                    JOIN kullanici k ON m.gonderen_id = k.kullanici_id
                    WHERE (m.gonderen_id = %s AND m.alici_id = %s) OR (m.gonderen_id = %s AND m.alici_id = %s)
                    ORDER BY m.gonderim_tarihi ASC
                """
                cursor.execute(sql, (session['user_id'], alici_id, alici_id, session['user_id']))
                mesajlar = cursor.fetchall()
                return jsonify(mesajlar), 200
    except Exception as e:
        print(f"Mesajlar alınırken hata: {e}")
        return jsonify({'error': 'Mesajlar alınırken bir hata oluştu!'}), 500

@app.route('/api/gruba_uye_ekle', methods=['POST'])
def gruba_uye_ekle():
    data = request.json
    grup_id = data.get('grup_id')
    kullanici_id = data.get('kullanici_id')

    if not grup_id or not kullanici_id:
        return jsonify({'error': 'Grup ID veya Kullanıcı ID boş olamaz!'}), 400

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM grup_uyeleri WHERE grup_id = %s AND kullanici_id = %s"
                cursor.execute(sql, (grup_id, kullanici_id))
                if cursor.fetchone():
                    return jsonify({'error': 'Kullanıcı zaten bu grupta!'}), 400

                sql = "INSERT INTO grup_uyeleri (grup_id, kullanici_id) VALUES (%s, %s)"
                cursor.execute(sql, (grup_id, kullanici_id))
                connection.commit()

                return jsonify({'message': 'Kullanıcı gruba eklendi!'}), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Kullanıcı gruba eklenirken bir hata oluştu!'}), 500

@socketio.on('send_group_message')
def handle_send_group_message(data):
    gonderen_id = session.get('user_id')
    grup_id = data.get('grup_id')
    icerik = data.get('icerik')

    if not gonderen_id or not grup_id or not icerik:
        emit('error', {'message': 'Eksik bilgi!'})
        return

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Mesajı veritabanına kaydet (okundu=False olarak)
                sql = "INSERT INTO mesaj (gonderen_id, grup_id, icerik, okundu) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (gonderen_id, grup_id, icerik, False))
                connection.commit()

                # Gönderenin kullanıcı adını al
                sql = "SELECT kullanici_adi FROM kullanici WHERE kullanici_id = %s"
                cursor.execute(sql, (gonderen_id,))
                gonderen = cursor.fetchone()

                # Mesajı gruba gönder
                emit('receive_group_message', {
                    'gonderen_id': gonderen_id,
                    'gonderen_adi': gonderen['kullanici_adi'],
                    'grup_id': grup_id,
                    'icerik': icerik,
                    'okundu': False  # Mesaj henüz okunmadı
                }, room=f'grup_{grup_id}')
    except Exception as e:
        print(f"Grup mesajı gönderilirken hata: {e}")
        emit('error', {'message': 'Grup mesajı gönderilirken bir hata oluştu!'})

@socketio.on('mesaj_okundu')
def handle_mesaj_okundu(data):
    mesaj_id = data.get('mesaj_id')
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Mesajın okundu bilgisini güncelle
                sql = "UPDATE mesaj SET okundu = TRUE WHERE mesaj_id = %s"
                cursor.execute(sql, (mesaj_id,))
                connection.commit()

                # Güncellenen mesajı al
                sql = "SELECT * FROM mesaj WHERE mesaj_id = %s"
                cursor.execute(sql, (mesaj_id,))
                mesaj = cursor.fetchone()

                # Mesajın okundu bilgisini gruba bildir
                emit('mesaj_okundu_bildir', {
                    'mesaj_id': mesaj_id,
                    'okundu': True
                }, room=f'grup_{mesaj["grup_id"]}')
    except Exception as e:
        print(f"Mesaj okundu bilgisi güncellenirken hata: {e}")
        emit('error', {'message': 'Mesaj okundu bilgisi güncellenirken bir hata oluştu!'})

@socketio.on('join_group')
def handle_join_group(data):
    grup_id = data.get('grup_id')
    if grup_id:
        join_room(f'grup_{grup_id}')
        emit('group_joined', {'grup_id': grup_id})

@app.route('/api/kullanicilar', methods=['GET'])
def get_kullanicilar():
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                sql = "SELECT kullanici_id, kullanici_adi FROM kullanici"
                cursor.execute(sql)
                kullanicilar = cursor.fetchall()
                return jsonify(kullanicilar), 200
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({'error': 'Kullanıcılar alınırken bir hata oluştu!'}), 500

@socketio.on('send_message')
def handle_send_message(data):
    gonderen_id = session.get('user_id')
    alici_id = data.get('alici_id')
    icerik = data.get('icerik')

    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Mesajı veritabanına kaydet
                sql = "INSERT INTO mesaj (gonderen_id, alici_id, icerik) VALUES (%s, %s, %s)"
                cursor.execute(sql, (gonderen_id, alici_id, icerik))
                connection.commit()

                # Mesajı alıcıya gönder
                emit('receive_message', {
                    'gonderen_id': gonderen_id,
                    'gonderen_adi': session.get('kullanici_adi'),
                    'alici_id': alici_id,
                    'icerik': icerik
                }, room=str(alici_id))

                # Mesajı gönderene de gönder
                emit('receive_message', {
                    'gonderen_id': gonderen_id,
                    'gonderen_adi': session.get('kullanici_adi'),
                    'alici_id': alici_id,
                    'icerik': icerik
                }, room=str(gonderen_id))
    except Exception as e:
        print(f"Mesaj gönderilirken hata: {e}")
        emit('error', {'message': 'Mesaj gönderilirken bir hata oluştu!'})

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    join_room(room)
    emit('room_joined', {'room': room})

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data.get('room')
    leave_room(room)
    emit('room_left', {'room': room})

if __name__ == '__main__':
    local_ip = get_local_ip()  # Yerel IP adresini al
    print(f"Uygulama şu IP üzerinde çalışıyor: http://{local_ip}:5005")
    socketio.run(app, host=local_ip, port=5005, debug=True)