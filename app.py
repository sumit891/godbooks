from flask import Flask, render_template, request, redirect, flash, url_for, session, Response
import os, json, requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_default_secret')

BASE_FOLDER = 'uploads'
CATEGORIES = ['jee', 'neet']
ALLOWED_DOC_EXTENSIONS = {'pdf', 'epub', 'txt', 'doc', 'docx'}
ALLOWED_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

BOOKS_FILE = "books.json"
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024

# Ensure uploads folder exists
os.makedirs(BASE_FOLDER, exist_ok=True)
for category in CATEGORIES:
    os.makedirs(os.path.join(BASE_FOLDER, category), exist_ok=True)

# Load books.json
def load_books():
    if os.path.exists(BOOKS_FILE):
        with open(BOOKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {c: [] for c in CATEGORIES}

def save_books(data):
    with open(BOOKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

books_data = load_books()

def allowed_file(filename, types):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in types

@app.route('/', methods=['GET'])
def home():
    query = request.args.get('q', '').lower()
    categorized_files = {}
    for category in CATEGORIES:
        filtered_books = []
        for book in books_data.get(category, []):
            if query and query not in book['file'].lower():
                continue
            filtered_books.append(book)
        categorized_files[category] = filtered_books
    return render_template("Book.html", files=categorized_files, is_admin=session.get('admin') == True, query=query)

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('✅ Logged in as admin')
            return redirect('/')
        else:
            flash('❌ Incorrect password')
            return redirect('/admin')
    return render_template("admin_login.html")

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash("Logged out successfully")
    return redirect('/')

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('admin'):
        flash('Unauthorized')
        return redirect('/admin')

    doc = request.files.get('book')
    img = request.files.get('cover')
    category = request.form.get('category')

    if category not in CATEGORIES:
        flash("Invalid category")
        return redirect('/')

    if doc and allowed_file(doc.filename, ALLOWED_DOC_EXTENSIONS):
        try:
            # ✅ Upload to GoFile
            r = requests.post("https://upload.gofile.io/uploadfile", files={"file": (doc.filename, doc)})
            print("GoFile RAW RESPONSE:", r.text)  # Debug log

            res = r.json()
            if res.get("status") == "ok":
                gofile_data = res["data"]

                # Try to get directLink, otherwise fallback to downloadPage
                direct_link = gofile_data.get("directLink")
                if not direct_link:
                    direct_link = gofile_data.get("downloadPage")

                file_record = {
                    "file": doc.filename,
                    "direct_link": direct_link,
                    "image": None
                }

                # Save cover locally (only small images, PDFs stay on GoFile)
                if img and allowed_file(img.filename, ALLOWED_IMG_EXTENSIONS):
                    ext = os.path.splitext(img.filename)[1]
                    imgname = os.path.splitext(doc.filename)[0] + ext
                    img.save(os.path.join(BASE_FOLDER, category, imgname))
                    file_record["image"] = imgname

                books_data[category].append(file_record)
                save_books(books_data)

                flash('✅ Book uploaded successfully!')
            else:
                flash('❌ Failed to upload to GoFile')

        except Exception as e:
            print("Upload error:", str(e))
            flash("❌ Upload error: " + str(e))
    else:
        flash('❌ Invalid book file')

    return redirect('/')

@app.route('/download/<category>/<filename>')
def download_file(category, filename):
    if category not in CATEGORIES:
        return "Invalid category", 404

    # Find file in books.json
    for book in books_data.get(category, []):
        if book["file"] == filename:
            try:
                direct_link = book.get("direct_link")
                if not direct_link:
                    return "File link missing in record", 500

                r = requests.get(direct_link, stream=True)
                if r.status_code != 200:
                    return f"Error fetching file from GoFile (status {r.status_code})", 500

                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            except Exception as e:
                return f"Error fetching file: {e}", 500
    return "File not found", 404

# ✅ FIXED: Stream large PDF in browser without memory issue
@app.route('/view/<category>/<filename>')
def view_file(category, filename):
    if category not in CATEGORIES:
        return "Invalid category", 404

    for book in books_data.get(category, []):
        if book["file"] == filename:
            try:
                direct_link = book.get("direct_link")
                if not direct_link:
                    return "File link missing in record", 500

                r = requests.get(direct_link, stream=True)
                if r.status_code != 200:
                    return f"Error fetching file from GoFile (status {r.status_code})", 500

                return Response(
                    r.iter_content(chunk_size=8192),
                    content_type="application/pdf",
                    headers={
                        "Content-Disposition": f"inline; filename={filename}"
                    }
                )
            except Exception as e:
                return f"Error fetching file: {e}", 500
    return "File not found", 404

@app.route('/uploads/<category>/<filename>')
def serve_image(category, filename):
    path = os.path.join(BASE_FOLDER, category, filename)
    if os.path.exists(path):
        return Response(open(path, "rb"), content_type="image/*")
    return "Image not found", 404

if __name__ == '__main__':
    app.run(debug=True)
