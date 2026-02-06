from cryptography.fernet import Fernet

from app.config import get_settings


class TokenManager:
    def __init__(self):
        settings = get_settings()
        if settings.encryption_key:
            self._fernet = Fernet(settings.encryption_key.encode())
        else:
            self._fernet = None

    def encrypt_token(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Encryption key not configured")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt_token(self, ciphertext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Encryption key not configured")
        return self._fernet.decrypt(ciphertext.encode()).decode()


token_manager = TokenManager()
