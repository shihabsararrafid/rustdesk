import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str = '/data/management.db'
    session_seconds: int = 28800
    max_body_bytes: int = 2 * 1024 * 1024
    public_origin: str = 'https://localhost'
    media_root: str | None = None
    media_quota_bytes: int = 20 * 1024**3
    media_asset_bytes: int = 2 * 1024**3
    media_retention_days: int = 30

    def __post_init__(self):
        if not self.public_origin.startswith('https://'):
            raise ValueError('Public origin must use HTTPS')
        if self.session_seconds <= 0 or not 1024 <= self.max_body_bytes <= 2 * 1024 * 1024:
            raise ValueError('Invalid lifetime or request limit')
        if min(self.media_quota_bytes, self.media_asset_bytes, self.media_retention_days) <= 0:
            raise ValueError('Invalid media limits')

    @classmethod
    def from_env(cls):
        return cls(database_path=os.environ.get('MANAGEMENT_DATABASE', '/data/management.db'),
                   session_seconds=int(os.environ.get('MANAGEMENT_SESSION_SECONDS', '28800')),
                   public_origin=os.environ.get('MANAGEMENT_PUBLIC_ORIGIN', 'https://localhost'),
                   media_root=os.environ.get('MANAGEMENT_MEDIA_ROOT'),
                   media_quota_bytes=int(os.environ.get('MANAGEMENT_MEDIA_QUOTA_BYTES', str(20 * 1024**3))),
                   media_retention_days=int(os.environ.get('MANAGEMENT_MEDIA_RETENTION_DAYS', '30')))
