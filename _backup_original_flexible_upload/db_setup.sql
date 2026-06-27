CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    country VARCHAR(100),
    organisation VARCHAR(150)
);

CREATE TABLE sites (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_email VARCHAR(150) NOT NULL,
    site_unit VARCHAR(150),
    compound VARCHAR(50),
    aquifer_thickness FLOAT,
    plume_length FLOAT,
    plume_width FLOAT,
    hydraulic_conductivity FLOAT,
    electron_donor FLOAT,
    electron_acceptor_o2 FLOAT,
    electron_acceptor_no3 FLOAT,
    extra_data TEXT,
    CONSTRAINT fk_sites_user_email
        FOREIGN KEY (user_email) REFERENCES users(email)
        ON DELETE CASCADE
);
