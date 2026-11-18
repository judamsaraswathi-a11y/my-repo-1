
import sqlite3
import bcrypt

def login_user(email, password):
    conn = sqlite3.connect("study_assistant.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, password, role FROM users WHERE email = ?",
        (email,)
    )

    user = cursor.fetchone()
    conn.close()

    if user:
        name, stored_password, role = user

        if bcrypt.checkpw(
            password.encode("utf-8"),
            stored_password.encode("utf-8")
        ):
            print("Login Successful!")
            print("Welcome:", name)
            print("Role:", role)
        else:
            print("Incorrect Password!")
    else:
        print("User Not Found!")


if __name__ == "__main__":
    login_user("student2@example.com", "student123")
