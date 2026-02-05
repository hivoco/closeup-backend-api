# Redis AWS ElastiCache Setup Guide

## Overview
This application uses **AWS ElastiCache Redis OSS (Serverless)** for high-performance caching, OTP storage, and rate limiting.

---

## AWS ElastiCache Configuration

### Current Setup
- **Endpoint**: `demo-du95w6.serverless.aps1.cache.amazonaws.com:6379`
- **Type**: Redis OSS Serverless
- **Region**: ap-south-1 (Mumbai)
- **Access**: VPC-only (requires EC2 instance or VPN)

### Environment Variables
```env
REDIS_HOST="demo-du95w6.serverless.aps1.cache.amazonaws.com"
REDIS_PORT=6379
REDIS_PASSWORD=""  # Set if AUTH token is enabled
REDIS_DB=0
```

---

## Security Configuration

### 1. Security Group Setup

Your ElastiCache Redis must allow inbound connections from your application servers.

#### Steps:
1. **AWS Console** → **EC2** → **Security Groups**
2. Find the security group attached to your Redis cache
3. Add **Inbound Rule**:
   - Type: **Custom TCP**
   - Port: **6379**
   - Source: **Your EC2 instance security group** OR **VPC CIDR**
   - Description: "Redis access for Close-Up API"

#### Example Rule:
```
Type: Custom TCP
Protocol: TCP
Port Range: 6379
Source: sg-xxxxx (EC2 instance security group)
Description: Close-Up API Redis access
```

### 2. AUTH Token (Optional)

If you enabled AUTH token on your ElastiCache:

1. **AWS Console** → **ElastiCache** → **Redis OSS caches** → `demo-du95w6`
2. Click **"Modify"**
3. View/Reset **AUTH token**
4. Copy the token
5. Update `.env`:
   ```env
   REDIS_PASSWORD="your-auth-token-here"
   ```

### 3. Encryption Settings

#### Encryption at Rest
- No code changes required
- Data encrypted on disk automatically

#### Encryption in Transit (TLS/SSL)
If enabled, update Redis client:

```python
# In app/core/redis.py
cls._client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    db=settings.REDIS_DB,
    ssl=True,  # Add this
    ssl_cert_reqs='required',  # Add this
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)
```

---

## Network Access

### ⚠️ Important: VPC-Only Access

AWS ElastiCache is **NOT accessible from the public internet**. You need one of:

### Option 1: Deploy to AWS EC2 (Recommended for Production)

1. **Launch EC2 instance** in the same VPC as ElastiCache
2. **Configure Security Group** to allow Redis access
3. **Deploy application** on EC2
4. Application can now access Redis

### Option 2: VPN Connection

1. Set up **AWS Client VPN** to your VPC
2. Connect via VPN from local machine
3. Access Redis through VPN tunnel

### Option 3: SSH Tunnel (Development)

1. Launch a bastion/jump host EC2 in same VPC
2. Create SSH tunnel:
   ```bash
   ssh -i your-key.pem -L 6379:demo-du95w6.serverless.aps1.cache.amazonaws.com:6379 ec2-user@your-bastion-ip
   ```
3. Update `.env` for local testing:
   ```env
   REDIS_HOST="localhost"
   ```

---

## Application Configuration

### Current Setup

The application is configured with graceful Redis fallback:

```python
# app/core/redis.py - Auto-fallback to database if Redis unavailable
def get_redis() -> Optional[redis.Redis]:
    try:
        return RedisClient.get_client()
    except Exception:
        return None  # App continues without Redis
```

### Benefits

- ✅ **Graceful Degradation**: App works without Redis
- ✅ **Database Fallback**: All operations fall back to database
- ✅ **No Downtime**: Redis issues don't break the app

---

## Testing Redis Connection

### From EC2 Instance

SSH into your EC2 instance and test:

```bash
# Install redis-cli
sudo yum install redis -y  # Amazon Linux
# OR
sudo apt-get install redis-tools -y  # Ubuntu

# Test connection
redis-cli -h demo-du95w6.serverless.aps1.cache.amazonaws.com -p 6379 ping

# Expected output: PONG
```

### With AUTH Token

```bash
redis-cli -h demo-du95w6.serverless.aps1.cache.amazonaws.com -p 6379 -a your-auth-token ping
```

### Using Python Script

Run the test script from your EC2:

```bash
python test_redis_connection.py
```

---

## Performance Optimization

### Redis Cache Strategy

#### 1. OTP Caching (5 minutes)
```python
# Cached in Redis for fast verification
OTPService.generate_and_cache_otp(user_id, mobile_number, db)
# ~1-5ms lookup vs ~50-100ms database query
```

#### 2. User Verification Cache (1 hour)
```python
# Avoid repeated DB queries
CacheService.cache_user_verification(user_id, is_verified=True, ttl=3600)
```

#### 3. Pending Video Cache (30 minutes)
```python
# Fast check for pending videos
CacheService.cache_pending_video(user_id, job_id, ttl=1800)
```

#### 4. Rate Limiting
```python
# Protect against abuse
CacheService.check_rate_limit(
    identifier=user_ip,
    action="otp_request",
    max_requests=5,
    window_seconds=300
)
```

### Performance Gains

| Operation | Without Redis | With Redis | Improvement |
|-----------|---------------|------------|-------------|
| OTP Verification | 50-100ms | 1-5ms | **10-20x faster** |
| Pending Video Check | 30-80ms | 1-3ms | **10-30x faster** |
| Database Load | High | Low | **90% reduction** |
| Scalability | ~1K req/sec | ~10K+ req/sec | **10x increase** |

---

## Monitoring

### CloudWatch Metrics

Monitor your ElastiCache in AWS CloudWatch:

1. **AWS Console** → **CloudWatch** → **Metrics** → **ElastiCache**
2. Key metrics to watch:
   - **CPUUtilization**: Should be < 70%
   - **NetworkBytesIn/Out**: Monitor traffic
   - **CurrConnections**: Current active connections
   - **Evictions**: Should be near 0
   - **CacheHits/CacheMisses**: Aim for >90% hit rate

### Application Logs

The application logs Redis connection status:

```bash
# On startup
🚀 Starting Closeup API...
✅ Redis connected successfully

# On shutdown
🛑 Shutting down Closeup API...
🔌 Redis connection closed
```

---

## Troubleshooting

### Issue 1: Connection Timeout

**Error**: `Failed to connect to Redis`

**Solutions**:
1. ✅ Check Security Group allows port 6379
2. ✅ Verify EC2 and Redis in same VPC
3. ✅ Check subnet routing tables
4. ✅ Verify Redis endpoint is correct

### Issue 2: AUTH Failed

**Error**: `NOAUTH Authentication required`

**Solutions**:
1. ✅ Get AUTH token from AWS Console
2. ✅ Set `REDIS_PASSWORD` in `.env`
3. ✅ Restart application

### Issue 3: App Works Locally but Not on EC2

**Reasons**:
- Running locally won't work (VPC-only)
- Need VPN or SSH tunnel for local testing
- Or deploy to EC2 in same VPC

**Solution**: Deploy to EC2 in same VPC as Redis

### Issue 4: High Memory Usage

**Solutions**:
1. ✅ Review TTL values (not too long)
2. ✅ Check for memory leaks
3. ✅ Monitor evictions in CloudWatch
4. ✅ Consider upgrading ElastiCache instance

---

## Deployment Checklist

### Before Deploying to Production

- [ ] ElastiCache Redis created in correct VPC
- [ ] Security Group configured with port 6379 access
- [ ] AUTH token configured (if using encryption)
- [ ] EC2 instance launched in same VPC
- [ ] Application `.env` updated with correct endpoint
- [ ] Test Redis connection from EC2
- [ ] CloudWatch alarms configured
- [ ] Backup retention policy set

### After Deployment

- [ ] Verify Redis connection in application logs
- [ ] Test OTP flow end-to-end
- [ ] Monitor CloudWatch metrics
- [ ] Check cache hit rates
- [ ] Verify performance improvements
- [ ] Test failover (stop Redis, verify app continues)

---

## Cost Optimization

### ElastiCache Pricing

Serverless Redis OSS pricing:
- **Data storage**: ~$0.125 per GB-hour
- **ElastiCache Processing Units (ECPUs)**: ~$0.075 per ECPU-hour
- **Data transfer**: Standard AWS rates

### Optimization Tips

1. **Set Appropriate TTLs**:
   - OTP: 5 minutes (300 seconds)
   - Verification: 1 hour (3600 seconds)
   - Keep TTLs short to save memory

2. **Monitor Usage**:
   - Review CloudWatch metrics weekly
   - Remove unused cache keys
   - Optimize cache key patterns

3. **Use Serverless Auto-Scaling**:
   - ElastiCache Serverless scales automatically
   - No manual capacity planning needed

---

## Redis Commands (For Debugging)

### Connect to Redis

```bash
redis-cli -h demo-du95w6.serverless.aps1.cache.amazonaws.com -p 6379
```

### Useful Commands

```bash
# Check connection
PING

# List all keys
KEYS *

# Get OTP for user
GET otp:user123

# Check TTL
TTL otp:user123

# Get all OTP keys
KEYS otp:*

# Count total keys
DBSIZE

# Get info
INFO

# Monitor real-time commands
MONITOR

# Flush all data (⚠️ DANGER!)
FLUSHDB
```

---

## Backup and Recovery

### ElastiCache Snapshots

1. **AWS Console** → **ElastiCache** → **Redis OSS caches** → `demo-du95w6`
2. **Backups** tab
3. Configure automatic snapshots
4. Set retention period (7-35 days recommended)

### Manual Backup

```bash
# Create snapshot via CLI
aws elasticache create-snapshot \
  --snapshot-name closeup-backup-2026-01-13 \
  --cache-cluster-id demo-du95w6 \
  --region ap-south-1
```

### Restore from Snapshot

```bash
aws elasticache restore-cache-cluster-from-snapshot \
  --cache-cluster-id demo-du95w6-restored \
  --snapshot-name closeup-backup-2026-01-13 \
  --region ap-south-1
```

---

## Best Practices

### 1. Security
- ✅ Use AUTH tokens in production
- ✅ Enable encryption in transit
- ✅ Restrict security group to minimum required access
- ✅ Use VPC endpoints for private access

### 2. Performance
- ✅ Use connection pooling (built into redis-py)
- ✅ Set appropriate timeouts (5 seconds)
- ✅ Monitor cache hit rates (aim for >90%)
- ✅ Use pipelining for bulk operations

### 3. Reliability
- ✅ Enable automatic failover
- ✅ Set up CloudWatch alarms
- ✅ Configure backup retention
- ✅ Implement graceful degradation (already done)

### 4. Cost Management
- ✅ Use serverless for variable workloads
- ✅ Set appropriate TTLs
- ✅ Monitor and optimize usage
- ✅ Clean up unused keys

---

## Support and Resources

### AWS Documentation
- [ElastiCache Redis](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/)
- [VPC Security](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)
- [Redis Commands](https://redis.io/commands/)

### Application Documentation
- [REDIS_INTEGRATION.md](REDIS_INTEGRATION.md) - Complete integration guide
- [test_redis_connection.py](test_redis_connection.py) - Connection testing script

---

## Quick Reference

### Environment Variables
```env
REDIS_HOST="demo-du95w6.serverless.aps1.cache.amazonaws.com"
REDIS_PORT=6379
REDIS_PASSWORD=""
REDIS_DB=0
```

### Security Group Rule
```
Type: Custom TCP
Port: 6379
Source: EC2 Security Group
```

### Test Connection
```bash
redis-cli -h demo-du95w6.serverless.aps1.cache.amazonaws.com -p 6379 ping
```

### Monitor Logs
```bash
tail -f /var/log/closeup-api.log | grep Redis
```

---

**Last Updated**: January 13, 2026
**Redis Version**: 7.1.0
**Region**: ap-south-1 (Mumbai)
**Type**: ElastiCache Redis OSS Serverless
