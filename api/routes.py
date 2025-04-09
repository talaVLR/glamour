from flask import request, jsonify, session
from flask import Blueprint
import requests
from api import api
import mysql.connector
import os
import base64
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app2 import log_activity


# Initialize the Blueprint
api = Blueprint('api', __name__)

# Database Connection
def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="12345",
        database="glamour"
    )
    return conn

@api.route('/login', methods=['POST'])
def login():
    email = request.json.get('email')
    password = request.json.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if email exists
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    # Debugging: Log the user object
    print("User  fetched from database:", user)

    if user:
        # Debugging: Log the hashed password
        print("Stored hashed password:", user['password'])
        print("Password provided for login:", password)

        # Check if the provided password matches the hashed password
        if check_password_hash(user['password'], password):
            # Store user session (ID)
            session['user_id'] = user['user_id']

            from app2 import log_activity

            log_activity(
                user_id=user['user_id'],
                action_type='login',
                description='User  logged in successfully',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User -Agent')  # Fixed typo
            )

            return jsonify({
                "message": "Login Successful",
                "user_id": user['user_id'],
                "name": user['name'],
                "email": user['email']
            }), 200
        else:
            return jsonify({"message": "Invalid email or password"}), 401
    else:
        return jsonify({"message": "Invalid email or password"}), 401

    
@api.route('/register', methods=['POST'])
def register():
    name = request.json.get('name')
    email = request.json.get('email')
    password = request.json.get('password')
    date_of_birth = request.json.get('date_of_birth')  # Expecting date in 'YYYY-MM-DD' format

    if not name or not email or not password or not date_of_birth:
        return jsonify({"message": "Name, email, password, and date of birth are required"}), 400

    # Validate date_of_birth format
    try:
        dob = datetime.strptime(date_of_birth, '%Y-%m-%d')
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Calculate age
    today = datetime.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if the email already exists
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        cursor.close()
        conn.close()
        return jsonify({"message": "Email already exists"}), 409

    # Hash the password
    hashed_password = generate_password_hash(password)

    # If email doesn't exist, insert the new user
    cursor.execute("""
        INSERT INTO users (name, email, password, age, dob) 
        VALUES (%s, %s, %s, %s, %s)
    """, (name, email, hashed_password, age, dob))

    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"message": "User  registered successfully"}), 201

@api.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({
        "message": "Logged out successfully"
    }), 200

# @api.route('/upload_image', methods=['POST'])
# def upload_image():
#     # 🔹 Get file and email safely
#     file = request.files.get('image')  # Avoid KeyError
#     email = request.form.get('email')

#     if not file:
#         return jsonify({'message': 'No image file provided'}), 400

#     if not email:
#         return jsonify({'message': 'Email is required'}), 400

#     email = email.strip().lower()  # Normalize email input
#     image_data = file.read()

#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)

#     try:
#         # 🔹 Check if user exists
#         cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
#         user = cursor.fetchone()

#         if not user:
#             return jsonify({'message': 'User  not found'}), 404

#         user_id = user['user_id']

#         # 🔹 Store image in `user_image` column (BLOB)
#         cursor.execute("""
#             UPDATE users
#             SET user_image = %s
#             WHERE email = %s
#         """, (image_data, email))

#         # 🔹 Send image to AI Model API
#         ai_api_url = 'https://219f-2a09-bac1-5aa0-40-00-247-24.ngrok-free.app/analyze'  # Replace if needed
#         response = requests.post(ai_api_url, files={'file': (file.filename, image_data)})

#         if response.status_code != 200:
#             return jsonify({'message': 'AI request failed', 'error': response.text}), 500

#         result = response.json()
        
#         if 'error' in result:
#             return jsonify({'message': 'AI error', 'error': result['error']}), 500

#         face_shape = result.get('face_shape')
#         skin_tone = result.get('skin_tone')

#         if not face_shape or not skin_tone:
#             return jsonify({'message': 'AI did not return valid data'}), 500

#         # 🔹 Get face_shape_id and skin_tone_id safely
#         cursor.execute("SELECT face_shape_id FROM face_shape WHERE face_shape_name = %s", (face_shape,))
#         face_shape_row = cursor.fetchone()
#         face_shape_id = face_shape_row['face_shape_id'] if face_shape_row else None

#         cursor.execute("SELECT skin_tone_id FROM skin_tone WHERE skin_tone_name = %s", (skin_tone,))
#         skin_tone_row = cursor.fetchone()
#         skin_tone_id = skin_tone_row['skin_tone_id'] if skin_tone_row else None

#         if not face_shape_id or not skin_tone_id:
#             return jsonify({'message': 'Face shape or skin tone not found'}), 404

#         # 🔹 Update user's face shape and skin tone
#         cursor.execute("""
#             UPDATE users
#             SET face_shape_id = %s, skin_tone_id = %s
#             WHERE email = %s
#         """, (face_shape_id, skin_tone_id, email))

#         # 🔹 Insert into recommendation
#         cursor.execute("""
#             INSERT INTO recommendation (user_id, face_shape_id, skin_tone_id)
#             VALUES (%s, %s, %s)
#         """, (user_id, face_shape_id, skin_tone_id))

#         conn.commit()  # Ensure changes are committed

#         return jsonify({
#             'message': 'Image processed successfully',
#             'face_shape': face_shape,
#             'skin_tone': skin_tone
#         }), 200

#     except Exception as e:
#         conn.rollback()  # Rollback in case of error
#         return jsonify({'message': 'An error occurred', 'error': str(e)}), 500

#     finally:
#         cursor.close()  # Ensure cursor is closed
#         conn.close()  # Ensure connection is closed

@api.route('/upload_image', methods=['POST'])
def upload_image():
    # 🔹 Get file and email safely
    file = request.files.get('image')  # Avoid KeyError
    email = request.form.get('email')

    if not file:
        return jsonify({'message': 'No image file provided'}), 400

    if not email:
        return jsonify({'message': 'Email is required'}), 400

    email = email.strip().lower()  # Normalize email input
    image_data = file.read()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 🔹 Check if user exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'message': 'User  not found'}), 404

        user_id = user['user_id']

        # 🔹 Store image in `user_image` column (BLOB)
        cursor.execute("""
            UPDATE users
            SET user_image = %s
            WHERE email = %s
        """, (image_data, email))

        # 🔹 Send image to AI Model API
        ai_api_url = 'https://219f-2a09-bac1-5aa0-40-00-247-24.ngrok-free.app/analyze'  # Replace if needed
        response = requests.post(ai_api_url, files={'file': (file.filename, image_data)})

        if response.status_code != 200:
            return jsonify({'message': 'AI request failed', 'error': response.text}), 500

        result = response.json()
        
        if 'error' in result:
            return jsonify({'message': 'AI error', 'error': result['error']}), 500

        face_shape = result.get('face_shape')
        skin_tone = result.get('skin_tone')

        if not face_shape or not skin_tone:
            return jsonify({'message': 'AI did not return valid data'}), 500

        # 🔹 Get face_shape_id and skin_tone_id safely
        cursor.execute("SELECT face_shape_id FROM face_shape WHERE face_shape_name = %s", (face_shape,))
        face_shape_row = cursor.fetchone()
        face_shape_id = face_shape_row['face_shape_id'] if face_shape_row else None

        cursor.execute("SELECT skin_tone_id FROM skin_tone WHERE skin_tone_name = %s", (skin_tone,))
        skin_tone_row = cursor.fetchone()
        skin_tone_id = skin_tone_row['skin_tone_id'] if skin_tone_row else None
        
        if not face_shape_id or not skin_tone_id:
            return jsonify({'message': 'Face shape or skin tone not found'}), 404

        # 🔹 Update user's face shape and skin tone
        cursor.execute("""
            UPDATE users
            SET face_shape_id = %s, skin_tone_id = %s
            WHERE email = %s
        """, (face_shape_id, skin_tone_id, email))

        # 🔹 Insert into recommendation
        cursor.execute("""
            INSERT INTO recommendation (user_id, face_shape_id, skin_tone_id)
            VALUES (%s, %s, %s)
        """, (user_id, face_shape_id, skin_tone_id))

        conn.commit()  # Ensure changes are committed

        return jsonify({
            'message': 'Image processed successfully',
            'face_shape': face_shape,
            'skin_tone': skin_tone
        }), 200

    except Exception as e:
        conn.rollback()  # Rollback in case of error
        print(f"Error occurred: {str(e)}")  # Log the error for debugging
        return jsonify({'message': 'An error occurred', 'error': str(e)}), 500

    finally:
        cursor.close()  # Ensure cursor is closed
        conn.close()  # Ensure connection is closed

@api.route('/user-profile', methods=['GET'])
def user_profile():
    # Get the user_id from the session or request
    user_id = request.args.get('user_id')  # Pass user_id as a query parameter
    if not user_id:
        return jsonify({"message": "User ID is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch user profile details
        cursor.execute("""
            SELECT 
                u.name, 
                u.age, 
                u.profile_pic, 
                fs.face_shape_name AS face_shape, 
                st.skin_tone_name AS skin_tone
            FROM users u
            LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
            LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
            WHERE u.user_id = %s
        """, (user_id,))
        user_profile = cursor.fetchone()

        if not user_profile:
            return jsonify({"message": "User not found"}), 404

        # Convert BLOB image to base64 if it exists
        profile_pic = None
        if user_profile['profile_pic']:
            profile_pic = base64.b64encode(user_profile['profile_pic']).decode('utf-8')

        # Prepare the response
        response = {
            "name": user_profile['name'],
            "age": user_profile['age'],
            "face_shape": user_profile['face_shape'],
            "skin_tone": user_profile['skin_tone'],
            "profile_pic": profile_pic
        }

        return jsonify(response), 200

    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return jsonify({"message": "An error occurred while fetching the profile"}), 500

    finally:
        cursor.close()
        conn.close()

@api.route('/edit-profile', methods=['POST'])
def edit_profile():
    # Get the user_id from the request
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({"message": "User  ID is required"}), 400

    # Get the fields to update
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    date_of_birth = request.form.get('date_of_birth')
    profile_picture = request.files.get('profile_picture')

    # Validate that at least one field is provided
    if not any([name, email, password, date_of_birth, profile_picture]):
        return jsonify({"message": "At least one field is required to update"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Check if the user exists
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"message": "User  not found"}), 404

        # Update the fields if provided
        if name:
            cursor.execute("UPDATE users SET name = %s WHERE user_id = %s", (name, user_id))
        if email:
            cursor.execute("UPDATE users SET email = %s WHERE user_id = %s", (email, user_id))
        if password:
            hashed_password = generate_password_hash(password)
            cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_password, user_id))
        if date_of_birth:
            try:
                dob = datetime.strptime(date_of_birth, '%Y-%m-%d')
                cursor.execute("UPDATE users SET date_of_birth = %s WHERE user_id = %s", (dob, user_id))
            except ValueError:
                return jsonify({"message": "Invalid date format. Use YYYY-MM-DD."}), 400
        if profile_picture:
            # Save the profile picture to a specific directory
            upload_folder = 'uploads'  # Change this to your desired upload folder
            os.makedirs(upload_folder, exist_ok=True)  # Create the directory if it doesn't exist

            # Save the file
            file_path = os.path.join(upload_folder, profile_picture.filename)
            profile_picture.save(file_path)

            # Update the profile picture path in the database
            cursor.execute("UPDATE users SET profile_pic = %s WHERE user_id = %s", (file_path, user_id))

        conn.commit()
        return jsonify({"message": "Profile updated successfully"}), 200

    except Exception as e:
        conn.rollback()
        print(f"Error updating profile: {e}")
        return jsonify({"message": "An error occurred while updating the profile"}), 500

    finally:
        cursor.close()
        conn.close()
