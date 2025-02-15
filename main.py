import os
import tkinter as tk
from tkinter import messagebox
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

LABEL_CATEGORIES = ["Landscape", "Family", "Vacation", "Portfolio"]

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
        
        ### ADDED: Maximize the main window ###
        # On Windows: root.state('zoomed') often works.
        # On Linux/macOS: root.attributes('-zoomed', True) or root.attributes('-fullscreen', True) might be required.
        # Try whichever approach suits your platform:
        # self.root.state('zoomed')  # Typically works on Windows.
        # self.root.attributes('-fullscreen', True)

        # self.root.attributes('-zoomed', True)  # Alternative for Linux/macOS (try if state('zoomed') doesn't work).
        
        self.image_dir = image_dir
        self.image_files = self.get_image_files(image_dir)
        self.current_index = 0
        self.conn = self.connect_to_db()

        if not self.image_files:
            messagebox.showerror("Error", "No images found in the directory!")
            root.destroy()
            return

        # For category keyboard shortcuts
        self.category_map = {
            "l": "Landscape",
            "f": "Family",
            "v": "Vacation",
            "p": "Portfolio"
        }

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

        # Category tiles (full category name displayed)
        self.label_var = tk.StringVar(value="")
        self.category_buttons = {}
        self.default_btn_bg = None  # Will store default background color

        for category in LABEL_CATEGORIES:
            btn = tk.Button(
                self.category_frame,
                text=category,
                width=12,
                height=2,
                command=lambda c=category: self.select_category(c),
                relief=tk.RAISED
            )
            btn.pack(pady=5)
            self.category_buttons[category] = btn
            if self.default_btn_bg is None:
                self.default_btn_bg = btn.cget("bg")

        # Save button
        self.save_button = tk.Button(self.controls_frame, text="Save", command=self.save_metadata)
        self.save_button.pack(side=tk.LEFT, padx=5)

        # Show filename of current image at bottom-right
        self.filename_label = tk.Label(self.controls_frame, text="")
        self.filename_label.pack(side=tk.RIGHT, padx=5)

        # Key bindings
        self.root.bind("<Key>", self.on_key_press)
        self.root.bind("<Return>", lambda e: self.save_metadata())

        ### ADDED: Bind left/right arrows to previous/next
        self.root.bind("<Left>", lambda e: self.previous_image())
        self.root.bind("<Right>", lambda e: self.next_image())

        self.load_image()

    def on_key_press(self, event):
        """Handle keyboard shortcuts for ratings (1-4), categories (l, f, v, p),
           and toggle mark-for-deletion (d)."""
        char = event.char.lower()

        # Ratings: 1-4
        if char in ['1', '2', '3', '4']:
            self.rating_var.set(int(char))

        # Categories: l, f, v, p
        if char in self.category_map:
            self.select_category(self.category_map[char])

        # Toggle mark-for-deletion: d
        if char == 'd':
            self.delete_var.set(not self.delete_var.get())

        # (Optionally, you could add a hotkey for "Do Not Delete".)

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
        Also clears previous selections. If the image cannot be opened,
        we still attempt to store a 'could not open image' record."""
        if not self.image_files:
            return

        # Clear all selections for new image
        self.delete_var.set(False)
        self.do_not_delete_var.set(False)
        self.rating_var.set(0)
        self.label_var.set("")
        for btn in self.category_buttons.values():
            btn.config(bg=self.default_btn_bg, fg="black",
                       activebackground=self.default_btn_bg,
                       activeforeground="black", relief=tk.RAISED)

        img_path = self.image_files[self.current_index]
        self.filename_label.config(text=os.path.basename(img_path))

        # Attempt to open the file
        try:
            image_extension = os.path.splitext(img_path)[1].lower()
            if image_extension in ['.nef', '.cr2', '.dng']:
                # Attempt to open RAW
                with rawpy.imread(img_path) as raw:
                    rgb = raw.postprocess()
                image = Image.fromarray(rgb)
            else:
                # For standard formats (JPEG, PNG, TIFF, etc.)
                image = Image.open(img_path)

            # Handle EXIF orientation
            exif_data = None
            try:
                exif_data = image._getexif()
            except Exception:
                pass

            if exif_data:
                orientation = exif_data.get(274)  # 274 is the Orientation tag
                if orientation == 3:
                    image = image.rotate(180, expand=True)
                elif orientation == 6:
                    image = image.rotate(270, expand=True)
                elif orientation == 8:
                    image = image.rotate(90, expand=True)

            # Resize & display
            # You can change the max size to fit your screen better if desired
            image.thumbnail((1400, 1000))
            self.tk_image = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.tk_image)
            self.root.title(f"Photo Catalog - {os.path.basename(img_path)}")

        except Exception as e:
            # If we cannot open or process the image, store partial info
            print(f"Could not open image {img_path} due to error: {e}")
            self.save_could_not_open_image(img_path)
            self.next_image()
            return

    def save_could_not_open_image(self, filepath):
        """
        Attempts to compute the file hash. If that fails, hash will be None.
        Inserts a record with label = 'could not open image' and minimal metadata.
        """
        if not self.conn:
            return  # Can't do anything if no DB connection

        file_hash = compute_file_hash(filepath)  # Might be None if it fails
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
        """Extracts EXIF metadata from an image file and converts file size to MB.
           Also computes the file hash."""
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

        # Compute file hash
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
        Saves the image metadata, rating, and label to the database and auto-scrolls to next image.
        The 'hash' is used as the primary key.
        """
        if not self.conn:
            messagebox.showerror("Database Error", "Not connected to database")
            return

        img_path = self.image_files[self.current_index]
        metadata = self.extract_metadata(img_path)

        rating = self.rating_var.get()
        label = self.label_var.get() if self.label_var.get() in LABEL_CATEGORIES else None
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
            label,
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

    def select_category(self, category):
        """Select the category, highlight the chosen tile with green background, un-highlight others."""
        self.label_var.set(category)
        for cat, btn in self.category_buttons.items():
            if cat == category:
                btn.config(bg="green", fg="white", activebackground="green",
                           activeforeground="green", relief=tk.SUNKEN)
            else:
                btn.config(bg=self.default_btn_bg, fg="black",
                           activebackground=self.default_btn_bg,
                           activeforeground="black", relief=tk.RAISED)

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
    app = PhotoCatalogApp(root, "/Volumes/T5 EVO/DateSortedImages/2024-01/")
    root.mainloop()
