import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import mysql.connector
import exifread

# Configure MySQL Connection
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'mysqlrootpw',
    'database': 'PhotoCatalog'
}

LABEL_CATEGORIES = ["Landscape", "Family", "Vacation", "Portfolio"]

class PhotoCatalogApp:
    def __init__(self, root, image_dir):
        self.root = root
        self.root.title("Photo Catalog App")

        self.image_dir = image_dir
        self.image_files = self.get_image_files(image_dir)
        self.current_index = 0
        self.conn = self.connect_to_db()

        if not self.image_files:
            messagebox.showerror("Error", "No images found in the directory!")
            root.destroy()
            return

        # UI Elements
        self.image_label = tk.Label(root)
        self.image_label.pack(expand=True)

        # Controls
        self.controls_frame = tk.Frame(root)
        self.controls_frame.pack(fill=tk.X)

        self.back_button = tk.Button(self.controls_frame, text="Back", command=self.previous_image)
        self.back_button.pack(side=tk.LEFT, padx=5)

        self.forward_button = tk.Button(self.controls_frame, text="Next", command=self.next_image)
        self.forward_button.pack(side=tk.LEFT, padx=5)

        self.delete_var = tk.BooleanVar()
        self.delete_check = tk.Checkbutton(self.controls_frame, text="Mark for Deletion", variable=self.delete_var)
        self.delete_check.pack(side=tk.LEFT, padx=5)

        self.rating_var = tk.IntVar(value=0)
        self.rating_label = tk.Label(self.controls_frame, text="Rating:")
        self.rating_label.pack(side=tk.LEFT, padx=5)

        for i in range(1, 5):
            rb = tk.Radiobutton(self.controls_frame, text=str(i), variable=self.rating_var, value=i)
            rb.pack(side=tk.LEFT)

        self.label_var = tk.StringVar()
        self.label_dropdown = ttk.Combobox(self.controls_frame, textvariable=self.label_var, values=LABEL_CATEGORIES)
        self.label_dropdown.set("Select Label")
        self.label_dropdown.pack(side=tk.LEFT, padx=5)

        self.save_button = tk.Button(self.controls_frame, text="Save", command=self.save_metadata)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.load_image()

    def get_image_files(self, directory):
        """Retrieve all image files in directory and subdirectories."""
        supported_formats = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff')
        image_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(supported_formats):
                    image_files.append(os.path.join(root, file))
        return sorted(image_files)

    def load_image(self):
        """Loads and displays the current image, rotating if necessary."""
        if not self.image_files:
            return

        img_path = self.image_files[self.current_index]
        image = Image.open(img_path)

        # Check if image has EXIF orientation tag and rotate accordingly
        try:
            exif = image._getexif()
            if exif:
                orientation = dict(exif).get(274)  # Orientation tag is 274
                if orientation == 3:
                    image = image.rotate(180, expand=True)
                elif orientation == 6:
                    image = image.rotate(270, expand=True)
                elif orientation == 8:
                    image = image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            pass  # No EXIF data or no orientation tag, skip rotation

        image.thumbnail((800, 600))
        self.tk_image = ImageTk.PhotoImage(image)

        self.image_label.config(image=self.tk_image)
        self.root.title(f"Photo Catalog - {os.path.basename(img_path)}")


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

    def connect_to_db(self):
        """Establishes a database connection."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except mysql.connector.Error as err:
            messagebox.showerror("Database Error", f"Error connecting to database: {err}")
            return None

    def extract_metadata(self, filepath):
        """Extracts EXIF metadata from an image file and converts file size to MB."""
        metadata = {
            "filename": os.path.basename(filepath),
            "filepath": filepath,
            "size": round(os.path.getsize(filepath) / (1024 * 1024), 2),  # Convert to MB
            "format": os.path.splitext(filepath)[1].replace('.', '').upper(),
            "date_created": None,
            "camera_model": None,
            "shutter_speed": None,
            "aperture": None,
        }

        try:
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f)

            metadata["date_created"] = str(tags.get("EXIF DateTimeOriginal", None))
            metadata["camera_model"] = str(tags.get("Image Model", None))
            metadata["shutter_speed"] = str(tags.get("EXIF ExposureTime", None))
            metadata["aperture"] = str(tags.get("EXIF FNumber", None))

        except Exception as e:
            print(f"EXIF Error: {e}")

        for key in metadata:
            if metadata[key] == "None":
                metadata[key] = None

        return metadata


    def save_metadata(self):
        """Saves the image metadata, rating, and label to the database and auto-scrolls to the next image."""
        if not self.conn:
            messagebox.showerror("Database Error", "Not connected to database")
            return

        img_path = self.image_files[self.current_index]
        metadata = self.extract_metadata(img_path)

        rating = self.rating_var.get()
        label = self.label_var.get() if self.label_var.get() in LABEL_CATEGORIES else None
        marked_for_deletion = self.delete_var.get()

        cursor = self.conn.cursor()
        query = """
        INSERT INTO Photos (filename, filepath, size, format, date_created, camera_model, 
                            shutter_speed, aperture, rating, label, marked_for_deletion, timestamp) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE 
            rating=VALUES(rating), 
            label=VALUES(label), 
            marked_for_deletion=VALUES(marked_for_deletion);
        """

        try:
            cursor.execute(query, (
                metadata["filename"], metadata["filepath"], metadata["size"], metadata["format"],
                metadata["date_created"], metadata["camera_model"],
                metadata["shutter_speed"], metadata["aperture"], rating, label, marked_for_deletion
            ))
            self.conn.commit()
        except mysql.connector.Error as err:
            messagebox.showerror("Database Error", f"Error saving metadata: {err}")
            cursor.close()
            return

        cursor.close()

        # Auto-scroll to next image
        self.next_image()


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoCatalogApp(root, "/Users/alanjackson/Pictures")
    root.mainloop()

# adding something else