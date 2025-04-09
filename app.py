from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, Response
import mysql.connector
import os
from api.routes import api
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import requests
import base64
import magic
from flask import send_file
from io import BytesIO



from flask_cors import CORS


app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
CORS(app)

app.register_blueprint(api, url_prefix='/api')

def fetch_dropdown_data(cursor):
    """Fetch skin tones, undertones, and shade types for dropdowns."""
    cursor.execute("SELECT * FROM skin_tone")
    skin_tones = cursor.fetchall()

    cursor.execute("SELECT * FROM undertone")
    undertones = cursor.fetchall()

    cursor.execute("SELECT * FROM makeup_shade_type")
    shade_types = cursor.fetchall()

    return skin_tones, undertones, shade_types


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
            # ✅ Check if the user exists in the `users` table
            cursor.execute("SELECT * FROM users WHERE email=%s AND password=%s", (email, password))
            user = cursor.fetchone()

            if user:
                # ✅ Check user type
                if user['user_type_id'] == 1:  # Admin
                    cursor.execute("SELECT * FROM admin WHERE user_id=%s", (user['user_id'],))
                    admin = cursor.fetchone()

                    if admin:
                        session['user_id'] = user['user_id']
                        session['user_type'] = 'Admin'
                        flash('Welcome, Admin!', 'success')
                        return redirect(url_for('admin_dashboard'))

                elif user['user_type_id'] == 2:  # Artist
                    cursor.execute("SELECT * FROM artist WHERE user_id=%s", (user['user_id'],))
                    artist = cursor.fetchone()

                    if artist:
                        session['user_id'] = user['user_id']
                        session['artist_id'] = artist['artist_id']  # 👈 IMPORTANT FOR ARTIST-SPECIFIC FEATURES
                        session['user_type'] = 'Artist'

                        if artist['approval_status'] == 'pending':
                            session.clear()  # 💅🔥 CLEAR SESSION IF PENDING!
                            flash("Your account is still pending approval. Please wait for an admin response.", "warning")
                            return redirect(url_for('pending_artist'))
                        
                        elif artist['approval_status'] == 'rejected':
                            session.clear()  # 💄🔥 CLEAR SESSION IF REJECTED!
                            flash("Your account has been rejected. Please contact support.", "danger")
                            return redirect(url_for('rejected_artist'))
                        
                        else:
                            flash('Welcome, Artist!', 'success')
                            return redirect(url_for('artist_dashboard'))

                else:  # Regular User
                    session['user_id'] = user['user_id']
                    session['user_type'] = 'User'
                    flash('Welcome!', 'success')
                    return redirect(url_for('user_dashboard'))  # 👈 ADD A ROUTE FOR REGULAR USERS

            # ✅ If no user found
            flash('Invalid credentials. Please try again.', 'danger')
            return render_template('login.html')

        except mysql.connector.Error as err:
            print(f"Database error: {err}")
            flash("An error occurred. Please try again later.", "danger")
            return render_template('login.html')

        finally:
            cursor.close()
            conn.close()

    # ✅ Handle GET requests (show the login page)
    return render_template('login.html')

# ✅ Pending Page
@app.route('/pending_artist')
def pending_artist():
    return '''
    <div style="text-align:center; padding:50px;">
        <h2 style="color:#d6336c;">💅 Pending Approval 💄</h2>
        <p>Your account is still under review. Please wait for an admin response.</p>
        <a href="/login" style="color:#d6336c;">Go Back to Login</a>
    </div>
    '''

# ✅ Rejected Page
@app.route('/rejected_artist')
def rejected_artist():
    return '''
    <div style="text-align:center; padding:50px;">
        <h2 style="color:#f63669;">💔 Rejected 💄</h2>
        <p>Your account has been rejected. Please contact support for further assistance.</p>
        <a href="/login" style="color:#f63669;">Go Back to Login</a>
    </div>
    '''

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

# @app.route('/artist/artist_suggestion')
# def artist_suggestions():
#     artist_id = session.get('artist_id')  # Get the logged-in artist's ID from the session
#     if not artist_id:
#         flash("You must be logged in to view suggestions.", "error")
#         return redirect(url_for('login'))

#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)

#     try:
#         # Fetch the artist's suggestions
#         cursor.execute("""
#             SELECT 
#                 asg.suggestion_id,
#                 asg.shade_id,
#                 asg.status,
#                 asg.created_at,
#                 asg.hex_code,
#                 asg.description,
#                 asg.image,
#                 asg.makeup_look_id,
#                 asg.shade_type_id,
#                 st.skin_tone_name,
#                 ut.undertone_name,
#                 ut.undertone_description,
#                 sht.shade_type_name,
#                 ml.makeup_look_name
#             FROM artist_suggestion asg
#             LEFT JOIN skin_tone st ON asg.skin_tone_id = st.skin_tone_id
#             LEFT JOIN undertone ut ON asg.undertone_id = ut.undertone_id
#             LEFT JOIN makeup_shade_type sht ON asg.shade_type_id = sht.shade_type_id
#             LEFT JOIN makeup_look ml ON asg.makeup_look_id = ml.makeup_look_id
#             WHERE asg.artist_id = %s
#         """, (artist_id,))
#         suggestions = cursor.fetchall()

#         # Fetch dropdown data
#         skin_tones, undertones, shade_types = fetch_dropdown_data(cursor)

#         # Check if there are no suggestions
#         no_suggestions = len(suggestions) == 0

#         return render_template(
#             'artist_suggestion.html',
#             suggestions=suggestions,
#             no_suggestions=no_suggestions,
#             skin_tones=skin_tones,
#             undertones=undertones,
#             shade_types=shade_types
#         )
#     except Exception as e:
#         flash(f"An error occurred: {str(e)}", "error")
#         return redirect(url_for('artist_dashboard'))
#     finally:
#         cursor.close()
#         conn.close()

# @app.route('/add_artist_suggestion', methods=['POST'])
# def add_artist_suggestion():
#     artist_id = session.get('artist_id')  # Get the logged-in artist's ID from the session
#     if not artist_id:
#         flash("You must be logged in to submit suggestions.", "error")
#         return redirect(url_for('login'))

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         # Get form data
#         shade_id = request.form['shade_id']
#         hex_code = request.form['hex_code']
#         skin_tone_id = request.form['skin_tone_id']
#         undertone_id = request.form['undertone_id']
#         description = request.form.get('description', '')
#         image = request.files['image'].read() if 'image' in request.files else None
#         makeup_look_id = request.form.get('makeup_look_id')  # Optional field
#         shade_type_id = request.form['shade_type_id']

#         # Insert into `artist_suggestion`
#         cursor.execute("""
#             INSERT INTO artist_suggestion (
#                 artist_id, shade_id, hex_code, skin_tone_id, undertone_id, 
#                 description, image, makeup_look_id, shade_type_id
#             )
#             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
#         """, (
#             artist_id,
#             shade_id,
#             hex_code,
#             skin_tone_id,
#             undertone_id,
#             description,
#             image,
#             makeup_look_id,
#             shade_type_id
#         ))

#         conn.commit()
#         flash("Suggestion submitted successfully!", "success")
#     except Exception as e:
#         flash(f"An error occurred: {str(e)}", "error")
#     finally:
#         cursor.close()
#         conn.close()

#     return redirect(url_for('artist_suggestions'))

# @app.route('/edit_artist_suggestion/<int:suggestion_id>', methods=['POST'])
# def edit_artist_suggestion(suggestion_id):
#     artist_id = session.get('artist_id')  # Get the logged-in artist's ID from the session
#     if not artist_id:
#         flash("You must be logged in to edit suggestions.", "error")
#         return redirect(url_for('login'))

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         # Get form data
#         shade_id = request.form['shade_id']
#         hex_code = request.form['hex_code']
#         skin_tone_id = request.form['skin_tone_id']
#         undertone_id = request.form['undertone_id']
#         description = request.form.get('description', '')
#         image = request.files['image'].read() if 'image' in request.files else None
#         makeup_look_id = request.form.get('makeup_look_id')  # Optional field
#         shade_type_id = request.form['shade_type_id']

#         # Update the suggestion
#         if image:
#             cursor.execute("""
#                 UPDATE artist_suggestion
#                 SET shade_id = %s, hex_code = %s, skin_tone_id = %s, undertone_id = %s, 
#                     description = %s, image = %s, makeup_look_id = %s, shade_type_id = %s
#                 WHERE suggestion_id = %s AND artist_id = %s
#             """, (
#                 shade_id, hex_code, skin_tone_id, undertone_id, description, 
#                 image, makeup_look_id, shade_type_id, suggestion_id, artist_id
#             ))
#         else:
#             cursor.execute("""
#                 UPDATE artist_suggestion
#                 SET shade_id = %s, hex_code = %s, skin_tone_id = %s, undertone_id = %s, 
#                     description = %s, makeup_look_id = %s, shade_type_id = %s
#                 WHERE suggestion_id = %s AND artist_id = %s
#             """, (
#                 shade_id, hex_code, skin_tone_id, undertone_id, description, 
#                 makeup_look_id, shade_type_id, suggestion_id, artist_id
#             ))

#         conn.commit()
#         flash("Suggestion updated successfully!", "success")
#     except Exception as e:
#         flash(f"An error occurred: {str(e)}", "error")
#     finally:
#         cursor.close()
#         conn.close()

#     return redirect(url_for('artist_suggestions'))

@app.route('/admin/dashboard')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

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

    return render_template('admin_dashboard.html',
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


# Manage Users - Display
@app.route('/admin/manageusers', methods=['GET'])
def admin_manage_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch all non-archived users
        cursor.execute("""
        SELECT 
            u.user_id, 
            u.name, 
            u.email, 
            u.age, 
            u.user_type_id, 
            ut.user_type_name, 
            a.artist_id, 
            a.approval_status,
            fs.face_shape_name, 
            st.skin_tone_name
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
            u.user_type_id, 
            ut.user_type_name, 
            a.artist_id, 
            a.approval_status,
            fs.face_shape_name, 
            st.skin_tone_name
        FROM users u
        LEFT JOIN usertype ut ON u.user_type_id = ut.user_type_id
        LEFT JOIN artist a ON u.user_id = a.user_id
        LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
        LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
        WHERE u.is_archived = 1
        """)
        archived_users = cursor.fetchall()

        cursor.execute("""
        SELECT 
            u.user_id, 
            u.name, 
            u.email, 
            u.age, 
            u.user_type_id, 
            ut.user_type_name, 
            a.artist_id, 
            a.approval_status,
            fs.face_shape_name, 
            st.skin_tone_name,
            u.is_archived  # Ensure this column is included
        FROM users u
        LEFT JOIN usertype ut ON u.user_type_id = ut.user_type_id
        LEFT JOIN artist a ON u.user_id = a.user_id
        LEFT JOIN face_shape fs ON u.face_shape_id = fs.face_shape_id
        LEFT JOIN skin_tone st ON u.skin_tone_id = st.skin_tone_id
        """)
        all_users = cursor.fetchall()

        # Filter users in Python
        enthusiasts = [user for user in all_users if user['user_type_id'] == 3]
        applicants = [user for user in all_users if user['user_type_id'] == 2 and user.get('approval_status') == 'pending']
        artists = [user for user in all_users if user['user_type_id'] == 2 and user.get('approval_status') in ('approved', 'rejected')]

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        all_users = []
        enthusiasts = []
        applicants = []
        artists = []
        archived_users = []
    finally:
        cursor.close()
        conn.close()

    return render_template(
        'admin_manage_users.html',
        all_users=all_users,
        enthusiasts=enthusiasts, 
        applicants=applicants,
        artists=artists,
        archived_users=archived_users
    )

    
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

# Approve Artist
@app.route('/approve_artist/<int:artist_id>', methods=['POST'])
def approve_artist(artist_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Make sure the artist exists and is pending
    cursor.execute("SELECT user_id FROM artist WHERE artist_id = %s AND approval_status = 'pending'", (artist_id,))
    artist = cursor.fetchone()

    if artist:
        cursor.execute("UPDATE artist SET approval_status='approved' WHERE artist_id=%s", (artist_id,))
        conn.commit()
        flash("Artist approved successfully!", "success")
    else:
        flash("Artist not found or already processed!", "warning")
    
    conn.close()
    return redirect(url_for('admin_manage_users'))


# Reject Artist
@app.route('/reject_artist/<int:artist_id>', methods=['POST'])
def reject_artist(artist_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if the artist is already rejected
    cursor.execute("SELECT approval_status FROM artist WHERE artist_id=%s", (artist_id,))
    artist = cursor.fetchone()
    
    if artist and artist[0] == 'rejected':
        flash("Artist is already rejected and cannot be rejected again.", "warning")
    else:
        # Update the artist status to rejected
        cursor.execute("UPDATE artist SET approval_status='rejected' WHERE artist_id=%s", (artist_id,))
        conn.commit()
        flash("Artist rejected successfully!", "danger")
    
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

    if new_status not in ['pending', 'approved', 'rejected']:
        flash("Invalid status!", "danger")
        return redirect(url_for('admin_manage_users'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE artist
        SET approval_status = %s
        WHERE artist_id = %s
    """, (new_status, artist_id))

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
               st.skin_tone_name, fs.face_shape_name
        FROM users u
        LEFT JOIN recommendations r ON u.recommendation_id = r.recommendation_id
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
    

@app.route('/user_image/<int:user_id>')
def user_image(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_image FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user or not user['user_image']:
            return send_file('static/default-profile.png', mimetype='image/png')
            
        return Response(user['user_image'], mimetype='image/jpeg')  # or detect type
    finally:
        cursor.close()
        conn.close()
        
#DATASET

@app.route('/admin/managedatasets', methods=['GET'])
def admin_manage_datasets():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch ALL Dataset Images (including those with NULL face_shape_id and skin_tone_id)
    cursor.execute("""
        SELECT 
            di.dataset_id, 
            COALESCE(di.data_image, u.user_image) AS data_image,  # Use data_image if available, otherwise user_image
            di.uploaded_at, di.is_archived,
            di.face_shape_id, di.skin_tone_id, di.confidence_score,
            fs.face_shape_name, st.skin_tone_name,
            u.name AS user_name, u.email
        FROM dataset_images di
        LEFT JOIN face_shape fs ON di.face_shape_id = fs.face_shape_id
        LEFT JOIN skin_tone st ON di.skin_tone_id = st.skin_tone_id
        LEFT JOIN users u ON di.user_id = u.user_id
        WHERE di.is_archived = 0
        ORDER BY di.uploaded_at DESC
    """)
    datasets = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_manage_datasets.html', datasets=datasets)

@app.route('/dataset_image/<int:dataset_id>', methods=['GET'])
def dataset_image(dataset_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT data_image 
        FROM dataset_images
        WHERE dataset_id = %s
    """, (dataset_id,))
    dataset = cursor.fetchone()
    cursor.close()
    conn.close()

    if not dataset or not dataset['data_image']:
        return "Image not found", 404

    # Return the image as a response
    return Response(dataset['data_image'], mimetype='image/jpeg')

@app.route('/admin/upload_dataset', methods=['POST'])
def upload_dataset():
    if 'image' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('admin_manage_datasets'))

    file = request.files['image']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('admin_manage_datasets'))

    if file:
        # Read the file as binary data
        file_data = file.read()

        # Insert binary data into dataset_images table
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO dataset_images (data_image) 
            VALUES (%s)
        """, (file_data,))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Dataset uploaded successfully!", "success")
        return redirect(url_for('admin_manage_datasets'))
    
@app.route('/admin/archive_dataset/<int:dataset_id>', methods=['POST'])
def archive_dataset(dataset_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE dataset_images
        SET is_archived = 1
        WHERE dataset_id = %s
    """, (dataset_id,))
    
    conn.commit()
    cursor.close()
    conn.close()

    flash("Dataset archived successfully!", "success")
    return redirect(url_for('admin_manage_datasets'))


@app.route('/trigger_prediction/<int:dataset_id>', methods=['POST'])
def trigger_prediction(dataset_id):
    # Fetch the binary image data from the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT data_image 
        FROM dataset_images 
        WHERE dataset_id = %s
    """, (dataset_id,))
    dataset = cursor.fetchone()
    cursor.close()
    conn.close()

    if not dataset:
        flash("Dataset not found.", "danger")
        return redirect(url_for('admin_manage_datasets'))

    # Prepare the binary image data to send to the AI Model API
    files = {
        'image': ('image.jpg', dataset['data_image'], 'image/jpeg')
    }

    # Send the image to the AI Model API
    try:
        response = requests.post('http://<their-server-ip>/predict', files=files)
        response_data = response.json()

        # Save the face_shape_id to the dataset_images table
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE dataset_images
            SET face_shape_id = %s,
                skin_tone_id = %s,
                confidence_score = %s,
            WHERE dataset_id = %s
        """, (
            response_data['face_shape_id'],
            response_data['skin_tone_id'],
            response_data['confidence_score'],  # Save only the face_shape_id
            dataset_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash("Prediction successful!", "success")
        return redirect(url_for('admin_manage_datasets'))

    except Exception as e:
        flash(f"Prediction failed: {e}", "danger")
        return redirect(url_for('admin_manage_datasets'))

@app.route('/admin/suggestions')
def suggestions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch all pending suggestions
        cursor.execute("""
            SELECT asg.*, 
                   u.name AS artist_name, 
                   ml.makeup_look_name, 
                   st.skin_tone_name, 
                   ut.undertone_name, 
                   ut.undertone_description,
                   mst.shade_type_name
            FROM artist_suggestion asg
            LEFT JOIN users u ON asg.artist_id = u.user_id
            LEFT JOIN makeup_look ml ON asg.makeup_look_id = ml.makeup_look_id
            LEFT JOIN skin_tone st ON asg.skin_tone_id = st.skin_tone_id
            LEFT JOIN undertone ut ON asg.undertone_id = ut.undertone_id
            LEFT JOIN makeup_shade_type mst ON asg.shade_type_id = mst.shade_type_id
            WHERE asg.status = 'Pending'
        """)
        suggestions = cursor.fetchall()

        # Fetch dropdown data
        skin_tones, undertones, shade_types = fetch_dropdown_data(cursor)

        # Convert BLOB images to base64 for display
        for suggestion in suggestions:
            if suggestion['image']:
                suggestion['image'] = base64.b64encode(suggestion['image']).decode('utf-8')

        no_suggestions = len(suggestions) == 0

        return render_template(
            'admin_suggestions.html', 
            suggestions=suggestions, 
            no_suggestions=no_suggestions,  
            skin_tones=skin_tones, 
            undertones=undertones,  
            shade_types=shade_types
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
        cursor.execute("""
            SELECT shade_name, hex_code
            FROM makeup_shades
            WHERE skin_tone_id = %s AND undertone_id = %s AND is_recommended = TRUE
        """, (skin_tone_id, undertone_id))
        recommended_shades = cursor.fetchall()

        if recommended_shades:
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
        # Get suggestion data
        cursor.execute("""
            SELECT shade_type_id, shade_name, description, hex_code, skin_tone_id, undertone_id, image 
            FROM artist_suggestion 
            WHERE suggestion_id = %s
        """, (suggestion_id,))
        suggestion = cursor.fetchone()

        if not suggestion:
            flash("Suggestion not found!", "danger")
            return redirect(url_for('suggestions'))

        # Insert into `makeup_shade`
        cursor.execute("""
            INSERT INTO makeup_shades (shade_type_id, shade_name, description, hex_code, skin_tone_id, undertone_id, image)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            suggestion['shade_type_id'],
            suggestion['shade_name'],
            suggestion['description'],
            suggestion['hex_code'],
            suggestion['skin_tone_id'],
            suggestion['undertone_id'],
            suggestion['image']
        ))

        # Mark suggestion as approved
        cursor.execute("""
            UPDATE artist_suggestion SET status = 'Approved' WHERE suggestion_id = %s
        """, (suggestion_id,))

        conn.commit()
        flash("Suggestion approved successfully!", "success")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
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
        shade_type_id = request.form['shade_type_id']  # Now using shade_type_id
        hex_code = request.form['hex_code']
        skin_tone_id = request.form['skin_tone_id']
        undertone_id = request.form['undertone_id']
        description = request.form['description']
        image = request.files['image'].read() if 'image' in request.files else None

        # 🔹 Update the suggestion with `shade_type_id`
        if image:
            cursor.execute("""
                UPDATE artist_suggestion
                SET shade_name = %s, shade_type_id = %s, hex_code = %s, 
                    skin_tone_id = %s, undertone_id = %s, description = %s, image = %s
                WHERE suggestion_id = %s
            """, (shade_name, shade_type_id, hex_code, skin_tone_id, undertone_id, description, image, suggestion_id))
        else:
            cursor.execute("""
                UPDATE artist_suggestion
                SET shade_name = %s, shade_type_id = %s, hex_code = %s, 
                    skin_tone_id = %s, undertone_id = %s, description = %s
                WHERE suggestion_id = %s
            """, (shade_name, shade_type_id, hex_code, skin_tone_id, undertone_id, description, suggestion_id))

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
        shade_type_id = request.form['shade_type_id']
        hex_code = request.form['hex_code']
        skin_tone_id = request.form['skin_tone_id']
        undertone_id = request.form['undertone_id']
        description = request.form['description']
        image = request.files['image'].read() if 'image' in request.files else None

        # Insert into `makeup_shade`
        cursor.execute("""
            INSERT INTO makeup_shades (shade_type_id, shade_name, description, hex_code, skin_tone_id, undertone_id, image, is_recommended)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
        """, (
            shade_type_id,
            shade_name,
            description,
            hex_code,
            skin_tone_id,
            undertone_id,
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000,debug=True)