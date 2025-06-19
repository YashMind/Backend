from cryptography.fernet import Fernet
from config import Settings

ENCRYPTION_KEY = Settings.ENCRYPTION_KEY
fernet = Fernet(ENCRYPTION_KEY)


def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    return fernet.decrypt(encrypted_data.encode()).decode()
