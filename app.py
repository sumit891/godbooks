from flask import Flask, render_template, request, redirect, flash, session, Response
import os, json, requests, datetime, traceback

app = Flask(__name__)
app.secret_key = "super_secret_key"

BASE_FOLDER = 'uploads'
CATEGORIES = ['jee', 'neet']
ALLOWED_DOC_EXTENSIONS = {'pdf'}
ALLOWED_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ADMIN_PASSWORD = "admin123"

BOOKS_FILE = "books.json"
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # ✅ 1 GB तक upload

# 🔑 Archive.org IAS3 Keys
ARCHIVE_ACCESS_KEY = "9A0i7CUUjQFnnIGX".strip()
ARCHIVE_SECRET_KEY = "KPn5ws69o3W0cysa".strip()

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

# ✅ Streaming Upload to Internet Archive
def upload_to_archive(file, category):
    item_id = f"{category}_{int(datetime.datetime.utcnow().timestamp())}"
    url = f"https://s3.us.archive.org/{item_id}/{file.filename}"

    headers = {
        "authorization": f"LOW {ARCHIVE_ACCESS_KEY}:{ARCHIVE_SECRET_KEY}",
        "x-archive-auto-make-bucket": "1",
        "x-archive-meta01-collection": "opensource",
        "x-archive-meta-mediatype": "texts",
        "x-archive-meta-language": "eng",
        "x-archive-meta-title": file.filename,
        "Content-Type": "application/pdf"
    }

    # ✅ streaming: file.stream से सीधे भेजो
    r = requests.put(
        url,
        data=file.stream,
        headers=headers
    )

    if r.status_code not in (200, 201):
        raise Exception(f"Archive upload failed: {r.text}")

    direct_link = f"https://archive.org/download/{item_id}/{file.filename}"
    details_link = f"https://archive.org/details/{item_id}"
    embed_code = f'<iframe src="https://archive.org/embed/{item_id}" width="560" height="384" frameborder="0" allowfullscreen></iframe>'

    return direct_link, details_link, embed_code


# ========================= Routes ========================= #

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
            # ✅ Upload to Archive.org
            direct_link, details_link, embed_code = upload_to_archive(doc, category)

            file_record = {
                "file": doc.filename,
                "direct_link": direct_link,
                "details_link": details_link,
                "embed_code": embed_code,
                "image": None
            }

            # Save cover locally
            if img and allowed_file(img.filename, ALLOWED_IMG_EXTENSIONS):
                ext = os.path.splitext(img.filename)[1]
                imgname = os.path.splitext(doc.filename)[0] + ext
                img.save(os.path.join(BASE_FOLDER, category, imgname))
                file_record["image"] = imgname

            books_data[category].append(file_record)
            save_books(books_data)

            flash('✅ Book uploaded successfully!')
        except Exception as e:
            # ✅ Error log capture + browser पर show
            error_msg = traceback.format_exc()
            print("Upload error:", error_msg)
            return f"<h3>❌ Internal Server Error</h3><pre>{error_msg}</pre>", 500
    else:
        flash('❌ Invalid book file')

    return redirect('/')


@app.route('/download/<category>/<filename>')
def download_file(category, filename):
    if category not in CATEGORIES:
        return "Invalid category", 404

    for book in books_data.get(category, []):
        if book["file"] == filename:
            link = book.get("direct_link")
            if not link:
                return "File link missing in record", 500

            r = requests.get(link, stream=True)
            return Response(
                r.iter_content(chunk_size=8192),
                content_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    return "File not found", 404


@app.route('/view/<category>/<filename>')
def view_file(category, filename):
    if category not in CATEGORIES:
        return "Invalid category", 404

    for book in books_data.get(category, []):
        if book["file"] == filename:
            link = book.get("direct_link")
            if not link:
                return "File link missing in record", 500

            r = requests.get(link, stream=True)
            return Response(
                r.iter_content(chunk_size=8192),
                content_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename={filename}"}
            )
    return "File not found", 404


@app.route('/uploads/<category>/<filename>')
def serve_image(category, filename):
    path = os.path.join(BASE_FOLDER, category, filename)
    if os.path.exists(path):
        return Response(open(path, "rb"), content_type="image/*")
    return "Image not found", 404


if __name__ == '__main__':
    app.run(debug=True)
