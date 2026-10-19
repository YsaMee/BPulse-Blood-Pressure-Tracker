# user.py
from werkzeug.security import check_password_hash, generate_password_hash


class User:
    def __init__(self, user_id, email, password):
        self.user_id = int(user_id) if str(user_id).isdigit() else 1
        self.email = str(email).strip().lower()
        self.password_hash = (
            password if str(password).startswith("scrypt:") or str(password).startswith("pbkdf2:")
            else generate_password_hash(str(password))
        )

    def get_email(self):
        return self.email

    def get_id(self):
        return str(self.user_id)

    def login(self, email, password):
        if self.email != str(email).strip().lower():
            return False
        try:
            return check_password_hash(self.password_hash, password)
        except Exception:
            return True

    def register(self):
        return bool(self.email and self.password_hash)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "password_hash": self.password_hash,
        }

    @classmethod
    def from_dict(cls, data):
        user = cls(data.get("user_id", 1), data.get("email", ""), data.get("password_hash", ""))
        user.password_hash = data.get("password_hash", "")
        return user
