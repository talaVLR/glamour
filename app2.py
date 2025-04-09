import random
import string
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, Response
import mysql.connector
import os
from api.routes import api
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import requests
import base64
from datetime import datetime 




from flask_cors import CORS


# Initialize the Flask application
app = Flask(__name__)

# Set the secret key for session management
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Enable Cross-Origin Resource Sharing (CORS)
CORS(app)




app.register_blueprint(api, url_prefix='/api')



def fetch_dropdown_data(cursor):
    """Fetch skin tones, undertones, and shade types for dropdowns."""
    cursor.execute("SELECT * FROM skin_tone")
    skin_tones = cursor.fetchall()

    cursor.execute("SELECT * FROM undertone")
    undertones = cursor.fetchall()

    cursor.execute("SELECT * FROM face_shape")
    face_shapes = cursor.fetchall()


    return skin_tones, undertones, face_shapes


# Database connection function
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="12345",
        database="glamour"
    )

# Dashboard route
@app.route('/')
def glamour():
    # Check if the user is already logged in
    if 'user_id' in session:
        # Redirect based on user role
        if session['user_type'] == 'Admin':
            return redirect(url_for('admin_dashboard'))
        elif session['user_type'] == 'Artist':
            return redirect(url_for('artist_dashboard'))
        else:
            return redirect(url_for('logout'))
    
    # IF NO ONE IS LOGGED IN, SHOW THE GLAMOUR PAGE
    return render_template('glamour.html', title="Glamour")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Get user with artist approval status
            cursor.execute("""
                SELECT u.*, a.approval_status 
                FROM users u
                LEFT JOIN artist a ON u.user_id = a.user_id
                WHERE u.email=%s AND u.password=%s
            """, (email, password))
            user = cursor.fetchone()

            if user:
                # Update last_login in users table (single update)
                cursor.execute("""
                    UPDATE users 
                    SET last_login = NOW() 
                    WHERE user_id = %s
                """, (user['user_id'],))
                conn.commit()

                # Set session variables
                session.update({
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'name': user['name'],
                    'user_type_id': user['user_type_id'],
                    'last_login': datetime.now().strftime('%B %d, %Y %I:%M %p')
                })

                # Handle profile picture
                if user.get('profile_pic'):
                    session['profile_pic'] = base64.b64encode(user['profile_pic']).decode('utf-8')
                elif user.get('profile_pic_path'):
                    session['profile_pic'] = user['profile_pic_path']

                # Log the login activity
                log_activity(
                    user_id=user['user_id'],
                    action_type='login',
                    description='Admin logged in successfully',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )

                # Redirect based on user type
                if user['user_type_id'] == 1:  # Admin
                    cursor.execute("SELECT admin_id FROM admin WHERE user_id=%s", (user['user_id'],))
                    if admin := cursor.fetchone():
                        session['admin_id'] = admin['admin_id']
                        flash('Admin login successful!', 'success')
                        return redirect(url_for('admin_dashboard'))

                elif user['user_type_id'] == 2:  # Artist
                    if user['approval_status'] == 'approved':
                        session['artist_id'] = user['artist_id'] if 'artist_id' in user else None
                        flash('Artist login successful!', 'success')
                        return redirect(url_for('artist_dashboard'))
                    elif user['approval_status'] == 'pending':
                        session.clear()
                        flash('Your artist account is pending approval', 'warning')
                        return redirect(url_for('pending_artist'))
                    else:  # rejected or other status
                        session.clear()
                        flash('Artist account not approved', 'danger')
                        return redirect(url_for('login'))

                else:  # Regular user (user_type_id == 3 or other)
                    flash('Login successful!', 'success')
                    return redirect(url_for('user_dashboard'))

            flash('Invalid email or password', 'danger')
            return render_template('glamour.html')

        except Exception as err:
            conn.rollback()
            print(f"Login error: {err}")
            flash('System error during login', 'danger')
            return render_template('glamour.html')

        finally:
            cursor.close()
            conn.close()

    return render_template('glamour.html')

# ✅ LOGOUT ROUTE
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('glamour'))

@app.route('/artist/dashboard')
def artist_dashboard():
    print("Session Data:", session)  # Debugging: Print session data

    if 'user_id' not in session or session['user_type'] != 'Artist':
        print("User not logged in or not an artist.")  # Debugging
        flash("You must log in first.", "danger")
        return redirect(url_for('login'))

    user_id = session.get('user_id')  # Use 'user_id' from session
    print(f"User ID: {user_id}")  # Debugging: Print user ID

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch artist approval status using `user_id`
        cursor.execute("SELECT approval_status FROM artist WHERE user_id = %s", (user_id,))
        artist = cursor.fetchone()
        print(f"Artist Approval Status: {artist}")  # Debugging: Print approval status

        if not artist:
            print("Artist record not found.")  # Debugging
            flash("Artist record not found. Please contact support.", "danger")
            return redirect(url_for('login'))

        if artist['approval_status'] == 'pending':
            print("Artist account pending approval.")  # Debugging
            flash("Your account is still pending approval.", "warning")
            return redirect(url_for('login'))
        elif artist['approval_status'] == 'rejected':
            print("Artist account rejected.")  # Debugging
            flash("Your account has been rejected.", "danger")
            return redirect(url_for('login'))

        # Fetch dropdown data
        skin_tones, undertones, shade_types = fetch_dropdown_data(cursor)
        print("Dropdown data fetched successfully.")  # Debugging

        # Fetch most common skin tone, face shape, and makeup look
        cursor.execute("SELECT st.skin_tone_name, COUNT(*) as count FROM recommendation r JOIN skin_tone st ON r.skin_tone_id = st.skin_tone_id GROUP BY st.skin_tone_name ORDER BY count DESC LIMIT 1")
        most_skin_tone = cursor.fetchone()
        print(f"Most Common Skin Tone: {most_skin_tone}")  # Debugging

        cursor.execute("SELECT fs.face_shape_name, COUNT(*) as count FROM recommendation r JOIN face_shape fs ON r.face_shape_id = fs.face_shape_id GROUP BY fs.face_shape_name ORDER BY count DESC LIMIT 1")
        most_face_shape = cursor.fetchone()
        print(f"Most Common Face Shape: {most_face_shape}")  # Debugging

        cursor.execute("SELECT ml.makeup_look_name, COUNT(*) as count FROM recommendation r JOIN makeup_look ml ON r.makeup_look_id = ml.makeup_look_id GROUP BY ml.makeup_look_name ORDER BY count DESC LIMIT 1")
        most_makeup_look = cursor.fetchone()
        print(f"Most Common Makeup Look: {most_makeup_look}")  # Debugging

        # Fetch artist's suggestions from the `artist_suggestion` table
        cursor.execute("""
            SELECT 
                asg.suggestion_id,
                asg.shade_id,
                asg.status,
                asg.created_at,
                asg.hex_code,
                asg.description,
                asg.image,
                st.skin_tone_name,
                ut.undertone_name,
                ml.makeup_look_name,
                sht.shade_type_name
            FROM artist_suggestion asg
            LEFT JOIN skin_tone st ON asg.skin_tone_id = st.skin_tone_id
            LEFT JOIN undertone ut ON asg.undertone_id = ut.undertone_id
            LEFT JOIN makeup_look ml ON asg.makeup_look_id = ml.makeup_look_id
            LEFT JOIN makeup_shade_type sht ON asg.shade_type_id = sht.shade_type_id
            WHERE asg.artist_id = %s
        """, (user_id,))
        suggestions = cursor.fetchall()
        print(f"Suggestions: {suggestions}")  # Debugging

        return render_template('artist_dashboard.html', 
                               most_skin_tone=most_skin_tone,
                               most_face_shape=most_face_shape,
                               most_makeup_look=most_makeup_look,
                               suggestions=suggestions,
                               skin_tones=skin_tones,
                               undertones=undertones,
                               shade_types=shade_types)

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        print(f"SQL Query: {cursor.statement}")  # Debugging: Print the last executed query
        flash("An error occurred while fetching data. Please try again later.", "danger")
        return redirect(url_for('login'))

    finally:
        cursor.close()
        conn.close()

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session.get('user_type_id') != 1:
        flash('Please login as admin first', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get admin profile from session
    admin_profile = {
        'user_id': session['user_id'],
        'name': session.get('name'),
        'email': session.get('email'),
        'profile_pic': session.get('profile_pic'),
        'role': 'Admin'
    }

    # Total Counts
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()['total_users']

    cursor.execute("SELECT COUNT(*) AS total_admins FROM users WHERE user_type_id = 1")
    total_admins = cursor.fetchone()['total_admins']

    cursor.execute("SELECT COUNT(*) AS total_artists FROM users WHERE user_type_id = 2")
    total_artists = cursor.fetchone()['total_artists']

    cursor.execute("SELECT COUNT(*) AS total_enthusiasts FROM users WHERE user_type_id = 3")
    total_enthusiasts = cursor.fetchone()['total_enthusiasts']

    # Top 3 Face Shapes
    cursor.execute("""
        SELECT f.face_shape_name, COUNT(u.face_shape_id) AS count 
        FROM users u 
        JOIN face_shape f ON u.face_shape_id = f.face_shape_id 
        WHERE u.face_shape_id IS NOT NULL 
        GROUP BY u.face_shape_id 
        ORDER BY count DESC 
        LIMIT 3
    """)
    top_face_shapes = cursor.fetchall()

    # Top 3 Skin Tones
    cursor.execute("""
        SELECT s.skin_tone_name, COUNT(u.skin_tone_id) AS count 
        FROM users u 
        JOIN skin_tone s ON u.skin_tone_id = s.skin_tone_id 
        WHERE u.skin_tone_id IS NOT NULL 
        GROUP BY u.skin_tone_id 
        ORDER BY count DESC 
        LIMIT 3
    """)
    top_skin_tones = cursor.fetchall()

    # Most Common Event
    cursor.execute("""
        SELECT m.makeup_look_name, COUNT(r.makeup_look_id) AS count 
        FROM recommendation r 
        JOIN makeup_look m ON r.makeup_look_id = m.makeup_look_id 
        GROUP BY r.makeup_look_id 
        ORDER BY count DESC 
        LIMIT 1
    """)
    most_common_event_result = cursor.fetchone()
    most_common_event = most_common_event_result['makeup_look_name'] if most_common_event_result else "N/A"

    # Most Recommended Shade
    cursor.execute("""
        SELECT m.makeup_look_name AS shade_name, COUNT(r.makeup_look_id) AS count 
        FROM recommendation r 
        JOIN makeup_look m ON r.makeup_look_id = m.makeup_look_id 
        GROUP BY r.makeup_look_id 
        ORDER BY count DESC 
        LIMIT 1
    """)
    most_recommended_shade_result = cursor.fetchone()
    most_recommended_shade = most_recommended_shade_result['shade_name'] if most_recommended_shade_result else "N/A"

    # Pending Applicants (users who applied to become artists)
    cursor.execute("""
        SELECT u.user_id, u.name, u.email, a.cert1, a.cert2, a.work1, a.work2, a.work3, a.approval_status 
        FROM users u 
        JOIN artist a ON u.user_id = a.user_id 
        WHERE a.approval_status = 'pending'
    """)
    pending_applicants = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS total_pending_suggestions FROM artist_suggestion WHERE status = 'pending'")
    total_pending_suggestions = cursor.fetchone()['total_pending_suggestions']

    cursor.close()
    conn.close()

    if admin_profile and admin_profile['profile_pic']:
        profile_pic_base64 = base64.b64encode(admin_profile['profile_pic']).decode('utf-8')
        admin_profile['profile_pic_base64'] = profile_pic_base64

    return render_template('admin_dashboard.html',
        admin_profile=admin_profile,
        total_users=total_users,
        total_admins=total_admins,
        total_artists=total_artists,
        total_enthusiasts=total_enthusiasts,
        top_face_shapes=top_face_shapes,
        top_skin_tones=top_skin_tones,
        most_common_event=most_common_event,
        most_recommended_shade=most_recommended_shade,
        pending_applicants=pending_applicants,
        total_pending_suggestions=total_pending_suggestions
    )


@app.route('/admin/update-profile-pic', methods=['POST'])
def update_profile_pic():
    if 'user_id' not in session:
        return redirect(url_for('glamour'))

    if 'profile_pic' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('admin_profile'))

    file = request.files['profile_pic']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin_profile'))

    try:
        # Option 1: Store as BLOB
        pic_data = file.read()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET profile_pic_blob = %s 
            WHERE user_id = %s
        """, (pic_data, session['user_id']))
        conn.commit()
        
        # Update session
        session['profile_pic'] = base64.b64encode(pic_data).decode('utf-8')
        flash('Profile picture updated!', 'success')

    except Exception as e:
        print(f"Error updating profile pic: {e}")
        flash('Failed to update profile picture', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_profile'))

# Manage Users - Display
@app.route('/admin/manageusers', methods=['GET'])
def admin_manage_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    admin_profile = {
        'user_id': session['user_id'],
        'name': session.get('name'),
        'email': session.get('email'),
        'profile_pic': session.get('profile_pic'),
        'role': 'Admin'
    }

    # Initialize all variables with default values
    all_users = []
    enthusiasts = []
    applicants = []
    artists = []
    archived_users = []
    rejected = []  # Initialize rejected here

    try:
        # Fetch all non-archived users
        cursor.execute("""
        SELECT 
            u.user_id, 
            u.name, 
            u.email, 
            u.age,
            u.dob,
            u.user_type_id, 
            ut.user_type_name, 
            a.artist_id, 
            a.approval_status,
            fs.face_shape_name, 
            st.skin_tone_name,
            u.created_at,
            u.user_image  
        FROM users u
        LEFT JOIN usertype ut ON u.user_type_id = ut.user_type_id
        LEFT JOIN artist a ON u.user_id = a.user_id
        LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
        LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
        WHERE u.is_archived = 0
        """)
        all_users = cursor.fetchall()

        # Fetch archived users
        cursor.execute("""
        SELECT 
            u.user_id, 
            u.name, 
            u.email, 
            u.age,
            u.dob,
            u.user_type_id, 
            ut.user_type_name, 
            a.artist_id, 
            a.approval_status,
            fs.face_shape_name, 
            st.skin_tone_name,
            u.user_image 
        FROM users u
        LEFT JOIN usertype ut ON u.user_type_id = ut.user_type_id
        LEFT JOIN artist a ON u.user_id = a.user_id
        LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
        LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
        WHERE u.is_archived = 1
        """)
        archived_users = cursor.fetchall()

        # Filter users in Python
        enthusiasts = [user for user in all_users if user['user_type_id'] == 3]
        applicants = [user for user in all_users if user['user_type_id'] == 2 and user.get('approval_status') == 'pending']
        artists = [user for user in all_users if user['user_type_id'] == 2 and user.get('approval_status') in ('approved', 'rejected')]
        rejected = [user for user in all_users if user['user_type_id'] == 2 and user.get('approval_status') == 'rejected']

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'admin_manage_users.html',
        admin_profile=admin_profile,
        rejected=rejected,
        all_users=all_users,
        enthusiasts=enthusiasts, 
        applicants=applicants,
        artists=artists,
        archived_users=archived_users
    )

# Add Admin Route
@app.route('/add_admin', methods=['POST'])
def add_admin():
    try:
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        dob = request.form.get('dob')
        permissions = request.form.getlist('permissions')  # Gets all checked permissions
        
        # Validate required fields
        if not all([name, email, dob]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('admin_manage_users'))
            
        # Check if email already exists
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("Email already exists", "danger")
            return redirect(url_for('admin_manage_users'))
        
        # Create new admin user
        password = generate_random_password()  # You'll need to implement this
        hashed_password = generate_password_hash(password)  # Use werkzeug.security
        
        # Insert into users table
        cursor.execute("""
            INSERT INTO users (name, email, password, dob, user_type_id, is_archived)
            VALUES (%s, %s, %s, %s, 1, 0)
        """, (name, email, hashed_password, dob))
        user_id = cursor.lastrowid
        
        # Insert into admin_permissions table (assuming you have one)
        for permission in permissions:
            cursor.execute("""
                INSERT INTO admin_permissions (user_id, permission)
                VALUES (%s, %s)
            """, (user_id, permission))
        
        conn.commit()
        
        # Send email with temporary password (implement this function)
        # send_admin_welcome_email(email, name, password)
        
        flash("Admin added successfully! Temporary password sent to their email.", "success")
        return redirect(url_for('admin_manage_users'))
        
    except Exception as e:
        conn.rollback()
        flash(f"Error adding admin: {str(e)}", "danger")
        return redirect(url_for('admin_manage_users'))
    finally:
        cursor.close()
        conn.close()

# Helper function to generate random password
def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(characters) for i in range(length))

# Archive User
@app.route('/archive_user/<int:user_id>', methods=['POST'])
def archive_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Archive user
    cursor.execute("UPDATE users SET is_archived = 1 WHERE user_id = %s", (user_id,))
    
    # Also archive artist profile if they are an artist
    cursor.execute("UPDATE artist SET approval_status = 'rejected' WHERE user_id = %s", (user_id,))
    
    conn.commit()
    cursor.close()
    conn.close()

    flash("User archived successfully!", "success")
    return redirect(url_for('admin_manage_users'))

@app.route('/unarchive_user/<int:user_id>', methods=['POST'])
def unarchive_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Unarchive user
        cursor.execute("UPDATE users SET is_archived = 0 WHERE user_id = %s", (user_id,))
        
        # If the user is an artist, reset their approval status to 'pending'
        cursor.execute("UPDATE artist SET approval_status = 'pending' WHERE user_id = %s", (user_id,))
        
        conn.commit()
        flash("User unarchived successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_manage_users'))

@app.route('/reapply_artist/<int:artist_id>', methods=['POST'])
def reapply_artist(artist_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE artist SET approval_status='pending' WHERE artist_id=%s", (artist_id,))
    conn.commit()
    
    cursor.close()
    conn.close()
    
    flash("Application submitted successfully! Please wait for approval.", "success")
    return redirect(url_for('artist_dashboard'))


# Edit Artist Status
@app.route('/edit_artist_status/<int:artist_id>', methods=['POST'])
def edit_artist_status(artist_id):
    new_status = request.form.get('status')
    verdict = request.form.get('verdict')

    if new_status not in ['pending', 'approved', 'rejected']:
        flash("Invalid status!", "danger")
        return redirect(url_for('admin_manage_users'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE artist
    SET approval_status = %s,
        verdict = %s,
        verdict_time = CURRENT_TIMESTAMP
    WHERE artist_id = %s
""", (new_status, verdict, artist_id))

    conn.commit()
    conn.close()

    flash("Artist status updated successfully!", "success")
    return redirect(url_for('admin_manage_users'))


#  User Details
@app.route('/view_user/<int:user_id>', methods=['GET'])
def view_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT u.name, u.email, u.age, u.user_image, u.feedback, 
               r.recommendation_name, ut.user_type_name, 
               st.skin_tone_name, fs.face_shape_name, u.created_at
        FROM users u
        LEFT JOIN recommendation r ON u.recommendation_id = r.recommendation_id
        LEFT JOIN user_types ut ON u.user_type_id = ut.user_type_id
        LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
        LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
        WHERE u.user_id = %s
    """, (user_id,))
    
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return render_template('view_user.html', user=user)
    

@app.route('/user_image/<int:user_id>', methods=['GET'])
def user_image(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT user_image 
        FROM users
        WHERE user_id = %s
    """, (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user or not user['user_image']:
        return "Image not found", 404

    # Return the image as a response
    return Response(user['user_image'], mimetype='image/jpeg')

#LOGS

@app.route('/admin/managedatasets', methods=['GET'])
def admin_manage_datasets():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    admin_profile = {
        'user_id': session['user_id'],
        'name': session.get('name'),
        'email': session.get('email'),
        'profile_pic': session.get('profile_pic'),
        'role': 'Admin'
    }

    # ======================
    # 1. RECOMMENDATION LOGS
    # ======================
    # Fetch all recommendation logs with related data
    cursor.execute("""
        SELECT 
            r.recommendation_id,
            r.user_id,
            u.name as user_name,
            u.email as user_email,
            COALESCE(st.skin_tone_name, u.skin_tone_id) as skin_tone,
            COALESCE(fs.face_shape_name, u.face_shape_id) as face_shape,
            ml.makeup_look_name as makeup_look,
            mt.makeup_type_name as makeup_type,
            s.shade_name as recommended_shade,
            r.created_at as timestamp
        FROM recommendation r
        LEFT JOIN users u ON r.user_id = u.user_id
        LEFT JOIN skin_tone st ON r.skin_tone_id = st.skin_tone_id
        LEFT JOIN face_shape fs ON r.face_shape_id = fs.face_shape_id
        LEFT JOIN makeup_look ml ON r.makeup_look_id = ml.makeup_look_id
        LEFT JOIN makeup_type mt ON r.makeup_type_id = mt.makeup_type_id
        LEFT JOIN makeup_shades s ON r.shade_id = s.shade_id
        ORDER BY r.created_at DESC
        LIMIT 50
    """)
    recommendations = cursor.fetchall()

    # Get distinct values for recommendation filters
    cursor.execute("SELECT DISTINCT COALESCE(st.skin_tone_name, u.skin_tone_id) as skin_tone FROM recommendation r LEFT JOIN skin_tone st ON r.skin_tone_id = st.skin_tone_id LEFT JOIN users u ON r.user_id = u.user_id WHERE COALESCE(st.skin_tone_name, u.skin_tone_id) IS NOT NULL")
    skin_tones = [t['skin_tone'] for t in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT COALESCE(fs.face_shape_name, u.face_shape_id) as face_shape FROM recommendation r LEFT JOIN face_shape fs ON r.face_shape_id = fs.face_shape_id LEFT JOIN users u ON r.user_id = u.user_id WHERE COALESCE(fs.face_shape_name, u.face_shape_id) IS NOT NULL")
    face_shapes = [s['face_shape'] for s in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT makeup_look_name FROM makeup_look")
    makeup_looks = [m['makeup_look_name'] for m in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT makeup_type_name FROM makeup_type")
    makeup_types = [m['makeup_type_name'] for m in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT shade_name FROM makeup_shades")
    shades = [s['shade_name'] for s in cursor.fetchall()]

    # Recommendation statistics
    cursor.execute("SELECT COUNT(*) as total FROM recommendation")
    total_recommendations = cursor.fetchone()['total']

    cursor.execute("""
        SELECT shade_name, COUNT(*) as count 
        FROM recommendation r
        JOIN makeup_shades s ON r.shade_id = s.shade_id
        GROUP BY shade_name 
        ORDER BY count DESC LIMIT 1
    """)
    common_shade = cursor.fetchone()

    cursor.execute("""
        SELECT COALESCE(st.skin_tone_name, u.skin_tone_id) as skin_tone, COUNT(*) as count 
        FROM recommendation r
        LEFT JOIN skin_tone st ON r.skin_tone_id = st.skin_tone_id
        LEFT JOIN users u ON r.user_id = u.user_id
        GROUP BY COALESCE(st.skin_tone_name, u.skin_tone_id)
        ORDER BY count DESC LIMIT 1
    """)
    common_skin_tone = cursor.fetchone()

    cursor.execute("""
    SELECT COALESCE(fs.face_shape_name, u.face_shape_id) as face_shape, COUNT(*) as count 
    FROM recommendation r
    LEFT JOIN face_shape fs ON r.face_shape_id = fs.face_shape_id  -- Join on ID
    LEFT JOIN users u ON r.user_id = u.user_id
    GROUP BY COALESCE(fs.face_shape_name, u.face_shape_id)
    ORDER BY count DESC LIMIT 1
    """)
    common_face_shape = cursor.fetchone()

    # ======================
    # 2. ACTIVITY LOGS
    # ======================
    cursor.execute("""
        SELECT 
            l.log_id,
            l.user_id,
            u.name as user_name,
            u.email as user_email,
            l.action_type,
            l.description,
            l.ip_address,
            l.user_agent,
            l.affected_record_id,
            l.affected_table,
            l.timestamp
        FROM activity_logs l
        JOIN users u ON l.user_id = u.user_id
        ORDER BY l.timestamp DESC
        LIMIT 50
    """)
    activities = cursor.fetchall()

    # Activity statistics
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT user_id) as active_users,
            SUM(action_type = 'login') as total_logins,
            SUM(action_type = 'recommendation') as recommendation_activities
        FROM activity_logs
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """)
    activity_stats = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('admin_manage_datasets.html',
        admin_profile=admin_profile,
        # Recommendation data
        recommendations=recommendations,
        skin_tones=skin_tones,
        face_shapes=face_shapes,
        makeup_looks=makeup_looks,
        makeup_types=makeup_types,
        shades=shades,
        total_recommendations=total_recommendations,
        most_common_shade=common_shade['shade_name'] if common_shade else 'N/A',
        most_common_skin_tone=common_skin_tone['skin_tone'] if common_skin_tone else 'N/A',
        most_common_face_shape=common_face_shape['face_shape'] if common_face_shape else 'N/A',
        # Activity data
        activities=activities,
        active_users=activity_stats['active_users'],
        total_logins=activity_stats['total_logins'],
        recommendation_activities=activity_stats['recommendation_activities']
    )

# ======================
# FILTER ENDPOINTS
# ======================

@app.route('/admin/filter_recommendations', methods=['POST'])
def filter_recommendations():
    filters = {
        'skin_tone': request.form.get('skin_tone'),
        'face_shape': request.form.get('face_shape'),
        'makeup_look': request.form.get('makeup_look'),
        'makeup_type': request.form.get('makeup_type'),
        'shade': request.form.get('shade')
    }
    print("Filters:", filters)  # Log the filters

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            r.recommendation_id,
            r.user_id,
            u.name as user_name,
            COALESCE(st.skin_tone_name, u.skin_tone_id) as skin_tone,
            COALESCE(fs.face_shape_name, u.face_shape_id) as face_shape,
            ml.makeup_look_name as makeup_look,
            mt.makeup_type_name as makeup_type,
            s.shade_name as recommended_shade,
            r.created_at as timestamp
        FROM recommendation r
        LEFT JOIN users u ON r.user_id = u.user_id
        LEFT JOIN skin_tone st ON r.skin_tone_id = st.skin_tone_id
        LEFT JOIN face_shape fs ON r.face_shape_id = fs.face_shape_id
        LEFT JOIN makeup_look ml ON r.makeup_look_id = ml.makeup_look_id
        LEFT JOIN makeup_type mt ON r.makeup_type_id = mt.makeup_type_id
        LEFT JOIN makeup_shades s ON r.shade_id = s.shade_id
        WHERE 1=1
    """
    params = []

    for field, value in filters.items():
        if value:
            if field == 'shade':
                query += " AND s.shade_name = %s"
                params.append(value)
            elif field in ['skin_tone', 'face_shape']:
                query += f" AND (COALESCE({'st.skin_tone_name' if field == 'skin_tone' else 'fs.face_shape_name'}, u.{field}_id) = %s"
                params.append(value)
            else:
                table = 'ml' if field == 'makeup_look' else 'mt'
                query += f" AND {table}.{field}_name = %s"
                params.append(value)

    query += " ORDER BY r.created_at DESC"
    print("Query:", query)  # Log the query
    print("Params:", params)  # Log the params

    cursor.execute(query, params)
    filtered_recommendations = cursor.fetchall()
    print("Filtered Recommendations:", filtered_recommendations)  # Log the results

    cursor.close()
    conn.close()

    return jsonify(filtered_recommendations)

@app.route('/admin/filter_activities', methods=['POST'])
def filter_activities():
    filters = {
        'user_id': request.form.get('user_id'),
        'action_type': request.form.get('action_type'),
        'start_date': request.form.get('start_date'),
        'end_date': request.form.get('end_date')
    }

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            l.log_id,
            l.user_id,
            u.name as user_name,
            l.action_type,
            l.description,
            l.ip_address,
            l.timestamp
        FROM activity_logs l
        JOIN users u ON l.user_id = u.user_id
        WHERE 1=1
    """
    params = []

    if filters['user_id']:
        query += " AND l.user_id = %s"
        params.append(filters['user_id'])
    
    if filters['action_type']:
        query += " AND l.action_type = %s"
        params.append(filters['action_type'])
    
    if filters['start_date']:
        query += " AND l.timestamp >= %s"
        params.append(filters['start_date'])
    
    if filters['end_date']:
        query += " AND l.timestamp <= %s"
        params.append(filters['end_date'])

    query += " ORDER BY l.timestamp DESC"

    cursor.execute(query, params)
    filtered_activities = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(filtered_activities)
        
@app.route('/admin/suggestions')
def suggestions():
    admin_profile = {
        'user_id': session['user_id'],
        'name': session.get('name'),
        'email': session.get('email'),
        'profile_pic': session.get('profile_pic'),
        'role': 'Admin'
    }

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch all pending suggestions
        cursor.execute("""
            SELECT asg.*, 
                   u.name AS artist_name, 
                   st.skin_tone_name, 
                   ut.undertone_name, 
                   ut.undertone_description
            FROM artist_suggestion asg
            LEFT JOIN users u ON asg.artist_id = u.user_id
            LEFT JOIN skin_tone st ON asg.skin_tone_id = st.skin_tone_id
            LEFT JOIN undertone ut ON asg.undertone_id = ut.undertone_id
            WHERE asg.status = 'Pending'
        """)
        suggestions = cursor.fetchall()

        # Fetch dropdown data (skin tones and undertones)
        cursor.execute("SELECT skin_tone_id, skin_tone_name FROM skin_tone")
        skin_tones = cursor.fetchall()

        cursor.execute("SELECT undertone_id, undertone_name FROM undertone")
        undertones = cursor.fetchall()

        cursor.execute("SELECT * FROM face_shape")
        face_shapes = cursor.fetchall()

        # Convert BLOB images to base64 for display
        for suggestion in suggestions:
            if suggestion['image']:
                suggestion['image'] = base64.b64encode(suggestion['image']).decode('utf-8')

            # Add hex codes to the suggestion for display
            suggestion['hex_codes'] = [
                suggestion['hex_code'],
                suggestion['hex_code_2'],
                suggestion['hex_code_3'],
                suggestion['hex_code_4'],
                suggestion['hex_code_5'],
                suggestion['hex_code_6'],
                suggestion['hex_code_7'],
                suggestion['hex_code_8']
            ]

        no_suggestions = len(suggestions) == 0

        return render_template(
            'admin_suggestions.html', 
            admin_profile=admin_profile,
            suggestions=suggestions, 
            no_suggestions=no_suggestions,  
            skin_tones=skin_tones, 
            undertones=undertones,
            face_shapes=face_shapes  # Assuming you have this data available
        )

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return f"Database error occurred: {err}", 500

    finally:
        cursor.close()
        conn.close()

@app.route('/get_recommended_colors', methods=['GET'])
def get_recommended_colors():
    skin_tone_id = request.args.get('skin_tone_id')
    undertone_id = request.args.get('undertone_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch recommended shades with all 8 hex codes
        cursor.execute("""
            SELECT shade_name, 
                   hex_code, hex_code_2, hex_code_3, hex_code_4, 
                   hex_code_5, hex_code_6, hex_code_7, hex_code_8
            FROM makeup_shades
            WHERE skin_tone_id = %s AND undertone_id = %s AND is_recommended = TRUE
        """, (skin_tone_id, undertone_id))
        recommended_shades = cursor.fetchall()

        if recommended_shades:
            # Add a 'hex_codes' field to each shade for easier frontend handling
            for shade in recommended_shades:
                shade['hex_codes'] = [
                    shade['hex_code'],
                    shade['hex_code_2'],
                    shade['hex_code_3'],
                    shade['hex_code_4'],
                    shade['hex_code_5'],
                    shade['hex_code_6'],
                    shade['hex_code_7'],
                    shade['hex_code_8']
                ]
            return jsonify(recommended_shades)
        else:
            return jsonify({"error": "No recommended shades found"}), 404

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return jsonify({"error": "Failed to fetch recommended shades"}), 500

    finally:
        cursor.close()
        conn.close()
        
@app.route('/approve_suggestion/<int:suggestion_id>', methods=['POST'])
def approve_suggestion(suggestion_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch the suggestion
        cursor.execute("""
            SELECT * FROM artist_suggestion WHERE suggestion_id = %s
        """, (suggestion_id,))
        suggestion = cursor.fetchone()

        if not suggestion:
            flash("Suggestion not found!", "danger")
            return redirect(url_for('suggestions'))

        # Check if it's a combination of shades or an application tip
        if suggestion['hex_code']:  # It's a combination of shades
            # Insert into `makeup_shades`
            cursor.execute("""
                INSERT INTO makeup_shades (
                    shade_name, description, 
                    hex_code, hex_code_2, hex_code_3, hex_code_4, 
                    hex_code_5, hex_code_6, hex_code_7, hex_code_8, 
                    artist_id, skin_tone_id, undertone_id, image, is_recommended
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                suggestion['shade_name'],  # Use a default name or allow editing
                suggestion['description'],
                suggestion['hex_code'],
                suggestion['hex_code_2'],
                suggestion['hex_code_3'],
                suggestion['hex_code_4'],
                suggestion['hex_code_5'],
                suggestion['hex_code_6'],
                suggestion['hex_code_7'],
                suggestion['hex_code_8'],
                suggestion['artist_id'],
                suggestion['skin_tone_id'],
                suggestion['undertone_id'],
                suggestion['image'],
                False  # Default is_recommended value
            ))

        else:  # It's an application tip
            # Insert into `application_tips`
            cursor.execute("""
                INSERT INTO application_tips (
                    tip, artist_id, created_at
                ) VALUES (%s, %s, NOW())
            """, (
                suggestion['description'],  # Use the description as the tip
                suggestion['artist_id']
            ))

        # Mark the suggestion as approved
        cursor.execute("""
            UPDATE artist_suggestion SET status = 'Approved' WHERE suggestion_id = %s
        """, (suggestion_id,))

        conn.commit()
        flash("Suggestion approved and added successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        conn.rollback()
        flash("Failed to approve suggestion.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('suggestions'))


@app.route('/reject_suggestion/<int:suggestion_id>', methods=['POST'])
def reject_suggestion(suggestion_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Mark Suggestion as Rejected
        cursor.execute("""
            UPDATE artist_suggestion SET status = 'Rejected' WHERE suggestion_id = %s
        """, (suggestion_id,))

        conn.commit()
        flash("Suggestion rejected successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        flash("Failed to reject suggestion.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('suggestions'))

@app.route('/edit_suggestion/<int:suggestion_id>', methods=['POST'])
def edit_suggestion(suggestion_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get form data
        shade_name = request.form['shade_name']
        hex_codes = [
            request.form.get('hex_code'),
            request.form.get('hex_code_2'),
            request.form.get('hex_code_3'),
            request.form.get('hex_code_4'),
            request.form.get('hex_code_5'),
            request.form.get('hex_code_6'),
            request.form.get('hex_code_7'),
            request.form.get('hex_code_8')
        ]
        skin_tone_id = request.form.get('skin_tone_id')
        undertone_id = request.form.get('undertone_id')
        description = request.form['description']
        image = request.files['image'].read() if 'image' in request.files else None

        # Update the suggestion
        if image:
            cursor.execute("""
                UPDATE artist_suggestion
                SET shade_name = %s, 
                    hex_code = %s, hex_code_2 = %s, hex_code_3 = %s, hex_code_4 = %s, 
                    hex_code_5 = %s, hex_code_6 = %s, hex_code_7 = %s, hex_code_8 = %s, 
                    skin_tone_id = %s, undertone_id = %s, description = %s, image = %s
                WHERE suggestion_id = %s
            """, (
                shade_name,
                *hex_codes,  # Unpack the list of hex codes
                skin_tone_id,
                undertone_id,
                description,
                image,
                suggestion_id
            ))
        else:
            cursor.execute("""
                UPDATE artist_suggestion
                SET shade_name = %s, 
                    hex_code = %s, hex_code_2 = %s, hex_code_3 = %s, hex_code_4 = %s, 
                    hex_code_5 = %s, hex_code_6 = %s, hex_code_7 = %s, hex_code_8 = %s, 
                    skin_tone_id = %s, undertone_id = %s, description = %s
                WHERE suggestion_id = %s
            """, (
                shade_name,
                *hex_codes,  # Unpack the list of hex codes
                skin_tone_id,
                undertone_id,
                description,
                suggestion_id
            ))

        conn.commit()
        flash("Suggestion updated successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        flash("Failed to update suggestion.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('suggestions'))

@app.route('/add_shade', methods=['POST'])
def add_shade():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get form data
        shade_name = request.form['shade_name']
        hex_codes = [
            request.form.get('hex_code'),
            request.form.get('hex_code_2'),
            request.form.get('hex_code_3'),
            request.form.get('hex_code_4'),
            request.form.get('hex_code_5'),
            request.form.get('hex_code_6'),
            request.form.get('hex_code_7'),
            request.form.get('hex_code_8')
        ]
        skin_tone_id = request.form.get('skin_tone_id')
        undertone_id = request.form.get('undertone_id')
        description = request.form['description']
        image = request.files['image'].read() if 'image' in request.files else None

        # Insert into `makeup_shades`
        cursor.execute("""
            INSERT INTO makeup_shades (
                shade_name, 
                hex_code, hex_code_2, hex_code_3, hex_code_4, 
                hex_code_5, hex_code_6, hex_code_7, hex_code_8, 
                skin_tone_id, undertone_id, description, image, is_recommended
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
        """, (
            shade_name,
            *hex_codes,  # Unpack the list of hex codes
            skin_tone_id,
            undertone_id,
            description,
            image
        ))

        conn.commit()
        flash("Shade added successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        flash("Failed to add shade.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('suggestions'))

@app.route('/add_tip', methods=['POST'])
def add_tip():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get form data
        face_shape_id = request.form.get('face_shape_id')
        tip = request.form.get('tip')

        # Validate required fields
        if not face_shape_id or not tip:
            flash("Face shape and tip are required.", "danger")
            return redirect(url_for('suggestions'))

        # Insert into `application_tips`
        cursor.execute("""
            INSERT INTO application_tips (
                face_shape_id, tip, created_at
            ) VALUES (%s, %s, NOW())
        """, (
            face_shape_id,
            tip
        ))

        conn.commit()
        flash("Application tip added successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        conn.rollback()
        flash("Failed to add application tip. Please try again.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('suggestions'))


@app.route('/admin/profile')
def admin_profile():
    # Default empty profile structure to prevent template errors
    default_profile = {
        'user_id': '',
        'name': 'Unknown',
        'email': '',
        'profile_pic': None,
        'role': 'Admin',
        'join_date': '',
        'last_login': 'Never',
        'activity_log': []
    }

    if 'user_id' not in session or session.get('user_type_id') != 1:
        flash('Please login as admin first', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get admin details (users table)
        cursor.execute("""
            SELECT 
                u.user_id, u.name, u.email, u.bio, u.profile_pic, u.created_at, u.last_login, a.admin_id
            FROM users u
            LEFT JOIN admin a on u.user_id = a.user_id
            WHERE u.user_id = %s AND u.user_type_id = 1
        """, (session['user_id'],))
        admin_data = cursor.fetchone()

        if not admin_data:
            flash('Admin profile not found', 'danger')
            return render_template('admin_profile.html', 
                               admin_profile=default_profile,
                               admin_stats={})

        # Get activity log (updated to use activity_logs table and user_id)
        cursor.execute("""
            SELECT 
                al.*, 
                u.name as admin_name
            FROM activity_logs al
            JOIN users u ON al.user_id = u.user_id
            WHERE al.user_id = %s
            ORDER BY al.timestamp DESC
            LIMIT 15
        """, (admin_data['user_id'],))
        activity_log = cursor.fetchall()

        # Prepare admin stats (updated to use activity_logs table and user_id)
        cursor.execute("""
            SELECT 
                COUNT(*) as total_actions,
                SUM(CASE WHEN DATE(timestamp) = CURDATE() THEN 1 ELSE 0 END) as recent_activity
            FROM activity_logs
            WHERE user_id = %s
        """, (admin_data['user_id'],))
        stats = cursor.fetchone()

        # Build the complete profile
        admin_profile = {
            'user_id': admin_data['user_id'],
            'admin_id': admin_data['admin_id'],
            'name': admin_data['name'],
            'bio': admin_data['bio'],
            'email': admin_data['email'],
            'profile_pic': admin_data.get('profile_pic'),
            'role': 'Admin',
            'join_date': admin_data['created_at'].strftime('%B %Y') if admin_data['created_at'] else '',
            'last_login': admin_data['last_login'].strftime('%B %d, %Y at %I:%M %p') if admin_data['last_login'] else 'Never',
            'activity_log': activity_log
        }

        # Convert BLOB image if exists
        if admin_profile['profile_pic'] and isinstance(admin_profile['profile_pic'], bytes):
            admin_profile['profile_pic'] = base64.b64encode(admin_profile['profile_pic']).decode('utf-8')

        # Prepare stats
        admin_stats = {
            'total_actions': stats['total_actions'] if stats else 0,
            'recent_activity': stats['recent_activity'] if stats else 0,
            'managed_users': 0  # You'll need to add your own query for this
        }

        return render_template('admin_profile.html',
                           admin_profile=admin_profile,
                           admin_stats=admin_stats)

    except Exception as e:
        print(f"Error fetching admin profile: {e}")
        flash("An error occurred while loading your profile", "danger")
        return render_template('admin_profile.html',
                           admin_profile=default_profile,
                           admin_stats={})
    finally:
        cursor.close()
        conn.close()


def log_activity(user_id=None, action_type=None, description=None, 
                 ip_address=None, user_agent=None, affected_record_id=None, 
                 affected_table=None):
    """
    Logs an activity for any user (admin, artist, or regular user).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        print(f"Logging activity for user_id: {user_id}")  # Debugging

        # Insert the log entry into the activity_logs table
        cursor.execute("""
            INSERT INTO activity_logs (
                user_id, action_type, description, ip_address, user_agent,
                affected_record_id, affected_table
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, 
            action_type or 'general',
            description or 'No description provided',
            ip_address,
            user_agent,
            affected_record_id,
            affected_table
        ))
        conn.commit()
        print("Activity logged successfully")  # Debugging
        return True
        
    except Exception as e:
        print(f"Error logging activity: {e}")  # Debugging
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000,debug=True)