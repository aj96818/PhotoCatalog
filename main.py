import os
import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
import exifread
import hashlib
from PIL import Image, ImageTk
import rawpy
import numpy as np
from datetime import datetime

# Configure MySQL Connection
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'mysqlrootpw',
    'database': 'PhotoCatalog'
}

LABEL_CATEGORIES = [
    "people", "city", "landscape", "water", "gf", "family",
    "portfolio", "objects", "animals", "trees", "seasonal",
    "nature", "abstract", "macro"
]

def compute_file_hash(filepath):
    """
    Compute and return the SHA-256 hash of a file.
    Returns None if the file cannot be read.
    """
    try:
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None

class PhotoCatalogApp:
    def __init__(self, root, image_dir):
        self.root = root
        self.root.title("Photo Catalog App")

        # === TTK STYLE SETUP ===
        style = ttk.Style()
        # Use a theme that generally honors background color settings
        style.theme_use("clam")

        # Unselected style
        style.configure(
            "UnselectedCategory.TButton",
            font=("Helvetica", 12),
            foreground="black",
            background="#d9d9d9",  # typical default button color
            # For some themes, you may also need to specify relief/border
        )

        # Selected style
        style.configure(
            "SelectedCategory.TButton",
            font=("Helvetica", 12),
            foreground="black",
            background="light green"
        )

        self.image_dir = image_dir
        self.image_files = self.get_image_files(image_dir)
        self.current_index = 0
        self.conn = self.connect_to_db()

        if not self.image_files:
            messagebox.showerror("Error", "No images found in the directory!")
            root.destroy()
            return

        # Maps key presses to categories
        self.category_map = {
            "p": "people",
            "c": "city",
            "l": "landscape",
            "w": "water",
            "g": "gf",
            "f": "family",
            "[": "portfolio",
            "o": "objects",
            "a": "animals",
            "t": "trees",
            "s": "seasonal",
            "n": "nature",
            "x": "abstract",
            "m": "macro"
        }

        # Reverse map so we know which key belongs to each category
        self.reverse_category_map = {v: k for k, v in self.category_map.items()}

        # Main frames
        self.top_frame = tk.Frame(root)
        self.top_frame.pack(fill=tk.BOTH, expand=True)

        # Frame for the image (left)
        self.image_label = tk.Label(self.top_frame)
        self.image_label.pack(side=tk.LEFT, expand=True)

        # Frame for the category tiles (right)
        self.category_frame = tk.Frame(self.top_frame)
        self.category_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Bottom controls
        self.controls_frame = tk.Frame(root)
        self.controls_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Navigation Buttons
        self.back_button = tk.Button(self.controls_frame, text="Back", command=self.previous_image)
        self.back_button.pack(side=tk.LEFT, padx=5)

        self.forward_button = tk.Button(self.controls_frame, text="Next", command=self.next_image)
        self.forward_button.pack(side=tk.LEFT, padx=5)

        # Mark for deletion
        self.delete_var = tk.BooleanVar()
        self.delete_check = tk.Checkbutton(
            self.controls_frame,
            text="Mark for Deletion",
            variable=self.delete_var
        )
        self.delete_check.pack(side=tk.LEFT, padx=5)

        # Do Not Delete
        self.do_not_delete_var = tk.BooleanVar()
        self.do_not_delete_check = tk.Checkbutton(
            self.controls_frame,
            text="Do Not Delete",
            variable=self.do_not_delete_var
        )
        self.do_not_delete_check.pack(side=tk.LEFT, padx=5)

        # Rating
        self.rating_var = tk.IntVar(value=0)
        self.rating_label = tk.Label(self.controls_frame, text="Rating:")
        self.rating_label.pack(side=tk.LEFT, padx=5)

        # Create radio buttons for rating (1-4)
        self.rating_buttons = []
        for i in range(1, 5):
            rb = tk.Radiobutton(
                self.controls_frame,
                text=str(i),
                variable=self.rating_var,
                value=i
            )
            rb.pack(side=tk.LEFT)
            self.rating_buttons.append(rb)

        self.selected_categories = set()
        self.category_buttons = {}

        # === CREATE THE CATEGORY BUTTONS AS TTK BUTTONS ===
        for category in LABEL_CATEGORIES:
            key_char = self.reverse_category_map.get(category, "")
            if key_char:
                btn_text = f"{category} ({key_char})"
            else:
                btn_text = category

            btn = ttk.Button(
                self.category_frame,
                text=btn_text,
                style="UnselectedCategory.TButton",
                command=lambda c=category: self.toggle_category(c)
            )
            btn.pack(pady=5)
            self.category_buttons[category] = btn

        # Save button
        self.save_button = tk.Button(self.controls_frame, text="Save", command=self.save_metadata)
        self.save_button.pack(side=tk.LEFT, padx=5)

        # Show filename of current image at bottom-right
        self.filename_label = tk.Label(self.controls_frame, text="")
        self.filename_label.pack(side=tk.RIGHT, padx=5)

        # Key bindings
        self.root.bind("<Key>", self.on_key_press)
        self.root.bind("<Return>", lambda e: self.save_metadata())
        self.root.bind("<Left>", lambda e: self.previous_image())
        self.root.bind("<Right>", lambda e: self.next_image())

        self.load_image()

    def on_key_press(self, event):
        """Handle keyboard shortcuts for toggling categories, ratings (1-4),
           and mark-for-deletion (d)."""
        char = event.char.lower()

        # Ratings: 1-4
        if char in ['1', '2', '3', '4']:
            self.rating_var.set(int(char))
            return

        # If it's in category_map, toggle that category
        if char in self.category_map:
            category = self.category_map[char]
            self.toggle_category(category)
            return

        # Toggle mark-for-deletion: d
        if char == 'd':
            self.delete_var.set(not self.delete_var.get())

    def toggle_category(self, category):
        """
        Toggle the category in selected_categories set.
        If it becomes selected, change style to "SelectedCategory.TButton".
        If deselected, revert style to "UnselectedCategory.TButton".
        """
        if category in self.selected_categories:
            self.selected_categories.remove(category)
            self.category_buttons[category].config(style="UnselectedCategory.TButton")
        else:
            self.selected_categories.add(category)
            self.category_buttons[category].config(style="SelectedCategory.TButton")

    def get_image_files(self, directory):
        """Retrieve all image files in directory and subdirectories."""
        supported_formats = (
            '.nef', '.dng', '.tiff', '.png', '.jpeg',
            '.jpg', '.cr2', '.bmp', '.gif'
        )
        image_files = []
        for root_dir, _, files in os.walk(directory):
            for file in files:
                # Skip hidden resource-fork files on macOS:
                if file.startswith("._"):
                    continue

                if file.lower().endswith(supported_formats):
                    image_files.append(os.path.join(root_dir, file))
        return sorted(image_files)

    def connect_to_db(self):
        """Establishes a database connection."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except mysql.connector.Error as err:
            messagebox.showerror("Database Error", f"Error connecting to database: {err}")
            return None

    def load_image(self):
        """Loads and displays the current image, rotating if necessary.
        Clears previous selections. If the image cannot be opened,
        store a partial record."""
        if not self.image_files:
            return

        # Clear checkboxes / rating for new image
        self.delete_var.set(False)
        self.do_not_delete_var.set(False)
        self.rating_var.set(0)

        # Reset all category buttons to unselected
        for cat in self.selected_categories:
            self.category_buttons[cat].config(style="UnselectedCategory.TButton")
        self.selected_categories.clear()

        img_path = self.image_files[self.current_index]
        self.filename_label.config(text=os.path.basename(img_path))

        try:
            image_extension = os.path.splitext(img_path)[1].lower()
            if image_extension in ['.nef', '.cr2', '.dng']:
                with rawpy.imread(img_path) as raw:
                    rgb = raw.postprocess()
                image = Image.fromarray(rgb)
            else:
                image = Image.open(img_path)

            # Handle EXIF orientation
            exif_data = None
            try:
                exif_data = image._getexif()
            except Exception:
                pass

            if exif_data:
                orientation = exif_data.get(274)
                if orientation == 3:
                    image = image.rotate(180, expand=True)
                elif orientation == 6:
                    image = image.rotate(270, expand=True)
                elif orientation == 8:
                    image = image.rotate(90, expand=True)

            # Resize & display
            image.thumbnail((1400, 1000))
            self.tk_image = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.tk_image)
            self.root.title(f"Photo Catalog - {os.path.basename(img_path)}")

        except Exception as e:
            print(f"Could not open image {img_path} due to error: {e}")
            self.save_could_not_open_image(img_path)
            self.next_image()
            return

    def save_could_not_open_image(self, filepath):
        """
        Attempts to compute the file hash. If that fails, hash will be None.
        Inserts a record with label='could not open image' and minimal metadata.
        """
        if not self.conn:
            return

        file_hash = compute_file_hash(filepath)
        cursor = self.conn.cursor()

        filename = os.path.basename(filepath)
        size_mb = None
        file_format = os.path.splitext(filepath)[1].replace('.', '').upper()
        camera_model = None
        date_created = None
        shutter_speed = None
        aperture = None

        query = """
        INSERT INTO Photos (hash, filename, filepath, size, format, date_created, camera_model,
                            shutter_speed, aperture, rating, label, marked_for_deletion, do_not_delete, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            filename=VALUES(filename),
            filepath=VALUES(filepath),
            size=VALUES(size),
            format=VALUES(format),
            date_created=VALUES(date_created),
            camera_model=VALUES(camera_model),
            shutter_speed=VALUES(shutter_speed),
            aperture=VALUES(aperture),
            rating=VALUES(rating),
            label=VALUES(label),
            marked_for_deletion=VALUES(marked_for_deletion),
            do_not_delete=VALUES(do_not_delete),
            timestamp=NOW();
        """

        data_tuple = (
            file_hash,
            filename,
            filepath,
            size_mb,
            file_format,
            date_created,
            camera_model,
            shutter_speed,
            aperture,
            0,  # rating
            "could not open image",  # label
            False,  # marked_for_deletion
            False,  # do_not_delete
        )

        try:
            cursor.execute(query, data_tuple)
            self.conn.commit()
        except mysql.connector.Error as err:
            print(f"Error inserting 'could not open image' record: {err}")
        finally:
            cursor.close()

    def extract_metadata(self, filepath):
        """Extract EXIF metadata from an image file and compute file hash."""
        metadata = {
            "filename": os.path.basename(filepath),
            "filepath": filepath,
            "size": round(os.path.getsize(filepath) / (1024 * 1024), 2),  # MB
            "format": os.path.splitext(filepath)[1].replace('.', '').upper(),
            "date_created": None,
            "camera_model": None,
            "shutter_speed": None,
            "aperture": None,
            "hash": None
        }

        metadata["hash"] = compute_file_hash(filepath)

        try:
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f)
            metadata["date_created"] = str(tags.get("EXIF DateTimeOriginal", None))
            metadata["camera_model"] = str(tags.get("Image Model", None))
            metadata["shutter_speed"] = str(tags.get("EXIF ExposureTime", None))
            metadata["aperture"] = str(tags.get("EXIF FNumber", None))
        except Exception as e:
            print(f"EXIF Error: {e}")

        # Convert "None" strings to real None
        for key in metadata:
            if metadata[key] == "None":
                metadata[key] = None

        return metadata

    def save_metadata(self):
        """
        Saves the image metadata, rating, and (multiple) label categories 
        as a comma-separated list in the DB. The 'hash' is used as the primary key.
        """
        if not self.conn:
            messagebox.showerror("Database Error", "Not connected to database")
            return

        img_path = self.image_files[self.current_index]
        metadata = self.extract_metadata(img_path)

        rating = self.rating_var.get()
        labels_csv = ",".join(sorted(self.selected_categories))
        marked_for_deletion = self.delete_var.get()
        do_not_delete = self.do_not_delete_var.get()

        cursor = self.conn.cursor()

        query = """
        INSERT INTO Photos (hash, filename, filepath, size, format, date_created, camera_model,
                            shutter_speed, aperture, rating, label, marked_for_deletion, do_not_delete, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            filename=VALUES(filename),
            filepath=VALUES(filepath),
            size=VALUES(size),
            format=VALUES(format),
            date_created=VALUES(date_created),
            camera_model=VALUES(camera_model),
            shutter_speed=VALUES(shutter_speed),
            aperture=VALUES(aperture),
            rating=VALUES(rating),
            label=VALUES(label),
            marked_for_deletion=VALUES(marked_for_deletion),
            do_not_delete=VALUES(do_not_delete),
            timestamp=NOW();
        """

        data_tuple = (
            metadata["hash"],
            metadata["filename"],
            metadata["filepath"],
            metadata["size"],
            metadata["format"],
            metadata["date_created"],
            metadata["camera_model"],
            metadata["shutter_speed"],
            metadata["aperture"],
            rating,
            labels_csv,
            marked_for_deletion,
            do_not_delete
        )

        try:
            cursor.execute(query, data_tuple)
            self.conn.commit()
        except mysql.connector.Error as err:
            messagebox.showerror("Database Error", f"Error saving metadata: {err}")
            cursor.close()
            return

        cursor.close()
        self.next_image()

    def next_image(self):
        """Moves to the next image."""
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.load_image()

    def previous_image(self):
        """Moves to the previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_image()

if __name__ == "__main__":
    root = tk.Tk()
    # Update this path to your actual image directory
    app = PhotoCatalogApp(root, "/Volumes/T5 EVO/DateSortedImages/2024-03")
    root.mainloop()
