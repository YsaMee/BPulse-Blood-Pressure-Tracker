# person.py
class Person:
    def __init__(self, person_id, name, user_id, age=45, gender="Unspecified"):
        self.person_id = int(person_id)
        self.name = str(name).strip()
        self.user_id = int(user_id) if str(user_id).isdigit() else 1
        self.age = int(age) if age and str(age).isdigit() else 45
        self.gender = str(gender).strip() if gender else "Unspecified"

    def get_name(self):
        return self.name

    def get_age(self):
        return self.age

    def get_gender(self):
        return self.gender

    def to_dict(self):
        return {
            "person_id": self.person_id,
            "id": self.person_id,
            "name": self.name,
            "user_id": self.user_id,
            "age": self.age,
            "gender": self.gender,
        }

    @classmethod
    def from_dict(cls, data):
        pid = data.get("person_id") or data.get("id", 1)
        return cls(
            pid,
            data.get("name", "Patient"),
            data.get("user_id", 1),
            age=data.get("age", 45),
            gender=data.get("gender", "Unspecified"),
        )
