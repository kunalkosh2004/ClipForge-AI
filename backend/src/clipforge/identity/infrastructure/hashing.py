from pwdlib import PasswordHash

from clipforge.identity.domain.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._ph = PasswordHash.recommended()

    def hash_password(self, password: str) -> str:
        return self._ph.hash(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        try:
            return self._ph.verify(password, hashed)
        except Exception:
            return False
