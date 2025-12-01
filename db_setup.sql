CREATE DATABASE cast_project;
USE cast_project;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100),
    email VARCHAR(150) UNIQUE,
    password_hash VARCHAR(255),
    country VARCHAR(100),
    organisation VARCHAR(150)
);

CREATE TABLE sites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_email VARCHAR(150),
    site_unit VARCHAR(150),
    compound VARCHAR(50),
    aquifer_thickness FLOAT,
    plume_length FLOAT,
    plume_width FLOAT,
    hydraulic_conductivity FLOAT,
    electron_donor FLOAT,
    electron_acceptor_o2 FLOAT,
    electron_acceptor_no3 FLOAT,
    FOREIGN KEY (user_email) REFERENCES users(email)
);
