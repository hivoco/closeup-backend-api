"""
Test Redis Connection Script
Run this to verify your Redis configuration
"""

import redis
import sys

# Your Redis configuration
REDIS_HOST = "demo-du95w6.serverless.aps1.cache.amazonaws.com"
REDIS_PORT = 6379
REDIS_PASSWORD = ""  # Empty if no password
REDIS_DB = 0

def test_connection():
    """Test Redis connection with different configurations"""

    print("=" * 60)
    print("Testing Redis Connection")
    print("=" * 60)
    print(f"Host: {REDIS_HOST}")
    print(f"Port: {REDIS_PORT}")
    print(f"DB: {REDIS_DB}")
    print(f"Password: {'(empty)' if not REDIS_PASSWORD else '(set)'}")
    print("=" * 60)
    print()

    # Test 1: No password, no SSL
    print("Test 1: Connecting without password and SSL...")
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        response = client.ping()
        print(f"✅ SUCCESS! PING response: {response}")
        print(f"✅ Connection works without password and SSL")

        # Test set and get
        client.set("test_key", "test_value", ex=10)
        value = client.get("test_key")
        print(f"✅ Set/Get works! Value: {value}")

        client.close()
        return True
    except redis.ConnectionError as e:
        print(f"❌ Connection failed: {e}")
    except redis.ResponseError as e:
        print(f"❌ Authentication failed: {e}")
        print("   → Try setting a password in REDIS_PASSWORD")
    except Exception as e:
        print(f"❌ Error: {e}")

    print()

    # Test 2: With password (if authentication is required)
    if not REDIS_PASSWORD:
        print("Test 2: Skipped (no password configured)")
        print()
    else:
        print("Test 2: Connecting with password...")
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            response = client.ping()
            print(f"✅ SUCCESS! PING response: {response}")
            print(f"✅ Connection works with password")
            client.close()
            return True
        except redis.ConnectionError as e:
            print(f"❌ Connection failed: {e}")
        except redis.ResponseError as e:
            print(f"❌ Authentication failed: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")

        print()

    # Test 3: With SSL (if encryption in transit is enabled)
    print("Test 3: Connecting with SSL/TLS...")
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            db=REDIS_DB,
            ssl=True,
            ssl_cert_reqs="required",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        response = client.ping()
        print(f"✅ SUCCESS! PING response: {response}")
        print(f"✅ Connection works with SSL/TLS")
        client.close()
        return True
    except redis.ConnectionError as e:
        print(f"❌ Connection failed: {e}")
    except redis.ResponseError as e:
        print(f"❌ Authentication failed: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print()
    return False


def print_recommendations():
    """Print recommendations based on test results"""
    print("=" * 60)
    print("Recommendations:")
    print("=" * 60)
    print()
    print("1. Check AWS Console:")
    print("   - Go to: AWS Console → ElastiCache → Redis OSS caches")
    print("   - Select: demo-du95w6")
    print("   - Check: Security settings")
    print()
    print("2. Verify Security Group:")
    print("   - Ensure your IP/EC2 has access to port 6379")
    print("   - Check VPC security group rules")
    print()
    print("3. Check AUTH Token:")
    print("   - If AUTH token is enabled, you need to set REDIS_PASSWORD")
    print("   - You can view/reset AUTH token in AWS Console")
    print()
    print("4. Check Encryption:")
    print("   - If 'Encryption in transit' is enabled, use ssl=True")
    print("   - If 'Encryption at rest' is enabled, no code changes needed")
    print()
    print("5. Network Access:")
    print("   - ElastiCache Redis is VPC-only")
    print("   - If running locally, you need VPN/Bastion host")
    print("   - If on EC2, ensure same VPC/subnet")
    print()


if __name__ == "__main__":
    print()
    success = test_connection()

    if not success:
        print_recommendations()
        sys.exit(1)
    else:
        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        print()
        print("Your .env configuration is correct:")
        print(f'REDIS_HOST="{REDIS_HOST}"')
        print(f'REDIS_PORT={REDIS_PORT}')
        print(f'REDIS_PASSWORD="{REDIS_PASSWORD}"')
        print(f'REDIS_DB={REDIS_DB}')
        print()
        sys.exit(0)
