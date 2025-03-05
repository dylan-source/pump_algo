from cryptography.fernet import Fernet

# Step 1: Generate a master encryption key (do this once and store it securely)
encryption_key = Fernet.generate_key()
print("Master Encryption Key (store this securely, NOT in your .env file):")
print(encryption_key.decode())

cipher = Fernet(encryption_key)

# Step 2: Provide your unencrypted private key as a string.
# This should be the base58 encoded private key that solana.py expects.
private_key = ""  # Replace with actual key

# Step 3: Encrypt the private key
encrypted_key = cipher.encrypt(private_key.encode())
print("\nEncrypted Private Key (copy this into your .env file as ENCRYPTED_PRIVATE_KEY):")
print(encrypted_key.decode())