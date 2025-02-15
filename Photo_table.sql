CREATE DATABASE PhotoCatalog;
USE PhotoCatalog;

-- drop table photos;

CREATE TABLE Photos (
    hash varchar(64) not null PRIMARY KEY,
    filename VARCHAR(255),
    filepath VARCHAR(255),
    size BIGINT,
    format VARCHAR(50),
    date_created DATETIME,
    camera_make VARCHAR(255),
    camera_model VARCHAR(255),
    shutter_speed VARCHAR(50),
    aperture VARCHAR(50),
    rating INT,
    label VARCHAR(50),
    marked_for_deletion BOOLEAN DEFAULT FALSE,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE Photos
  ADD COLUMN do_not_delete TINYINT(1) DEFAULT 0;

SELECT * FROM photos;

