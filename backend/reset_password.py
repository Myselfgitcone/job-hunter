"""
Reset a user's password directly in the database.

Usage:
    python reset_password.py
    python reset_password.py --email you@example.com --password newpassword123
    python reset_password.py --list     (list all registered users)
"""
import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def list_users():
    from database import SessionLocal, User
    from sqlalchemy import select
    async with SessionLocal() as db:
        result = await db.execute(select(User.email, User.name, User.created_at))
        users = result.fetchall()
        if not users:
            print("No users registered yet.")
            return
        print(f"\n{'Email':<35} {'Name':<20} {'Created'}")
        print("-" * 75)
        for email, name, created_at in users:
            print(f"{email:<35} {name:<20} {(created_at or '')[:19]}")
        print()


async def reset_password(email: str, new_password: str):
    from database import SessionLocal, User
    from auth import hash_password
    from sqlalchemy import select

    if len(new_password) < 8:
        print("❌ Password must be at least 8 characters.")
        return

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if not user:
            print(f"❌ No user found with email: {email}")
            print("   Run with --list to see all registered users.")
            return
        user.password_hash = hash_password(new_password)
        await db.commit()
        print(f"✅ Password reset successfully for {email}")
        print(f"   You can now log in with your new password.")


def main():
    parser = argparse.ArgumentParser(description="Job Hunter — Password Reset Tool")
    parser.add_argument("--email",    "-e", help="Email address to reset")
    parser.add_argument("--password", "-p", help="New password (min 8 chars)")
    parser.add_argument("--list",     "-l", action="store_true", help="List all users")
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_users())
        return

    if args.email and args.password:
        asyncio.run(reset_password(args.email, args.password))
        return

    # Interactive mode
    print("\n🔑  Job Hunter — Password Reset")
    print("=" * 40)
    asyncio.run(list_users())

    email = input("Enter your email address: ").strip()
    if not email:
        print("Cancelled.")
        return

    new_pass = input("Enter new password (min 8 chars): ").strip()
    if not new_pass:
        print("Cancelled.")
        return

    confirm = input("Confirm new password: ").strip()
    if new_pass != confirm:
        print("❌ Passwords don't match.")
        return

    asyncio.run(reset_password(email, new_pass))


if __name__ == "__main__":
    main()
