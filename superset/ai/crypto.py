# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Encryption helpers for AI provider credentials."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from hashlib import sha256

from flask import current_app
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    """Derive a stable Fernet key from Superset's application secret."""
    secret = current_app.config["SECRET_KEY"].encode()
    return Fernet(urlsafe_b64encode(sha256(secret).digest()))


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key before it is persisted."""
    return _fernet().encrypt(api_key.encode()).decode()


def decrypt_api_key(api_key_encrypted: str) -> str:
    """Decrypt a persisted API key only for provider construction."""
    return _fernet().decrypt(api_key_encrypted.encode()).decode()
