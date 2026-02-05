# Video Jobs API - Complete Examples

## Base URL
`http://localhost:8000/api/v1/video-jobs`

---

## All Filter Combinations with Examples

### 1. **No Filters - Get All Jobs**
```bash
GET /api/v1/video-jobs/list
```

**Response:**
```json
{
  "total": 500,
  "page": 1,
  "page_size": 20,
  "total_pages": 25,
  "filters_applied": {},
  "message": "Found 500 video job(s). Showing page 1 of 25.",
  "items": [...]
}
```

---

### 2. **Filter by Status Only**
```bash
GET /api/v1/video-jobs/list?status=failed
```

**Response:**
```json
{
  "total": 15,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "status": "failed"
  },
  "message": "Found 15 video job(s) with filters: status='failed'. Showing page 1 of 1.",
  "items": [...]
}
```

**Other Status Examples:**
- `?status=queued` - Get all queued jobs
- `?status=photo_processing` - Get jobs being processed
- `?status=uploaded` - Get completed jobs
- `?status=sent` - Get sent jobs

---

### 3. **Filter by Failed Stage Only**
```bash
GET /api/v1/video-jobs/list?failed_stage=photo
```

**Response:**
```json
{
  "total": 8,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "failed_stage": "photo"
  },
  "message": "Found 8 video job(s) with filters: failed_stage='photo'. Showing page 1 of 1.",
  "items": [...]
}
```

**Other Failed Stage Examples:**
- `?failed_stage=lipsync` - Get lipsync failures
- `?failed_stage=stitch` - Get stitching failures
- `?failed_stage=delivery` - Get delivery failures

---

### 4. **Filter by Date Range Only**
```bash
GET /api/v1/video-jobs/list?start_date=2026-01-01&end_date=2026-01-07
```

**Response:**
```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "filters_applied": {
    "start_date": "2026-01-01",
    "end_date": "2026-01-07"
  },
  "message": "Found 150 video job(s) with filters: from 2026-01-01, to 2026-01-07. Showing page 1 of 8.",
  "items": [...]
}
```

**Single Date (Today's Jobs):**
```bash
GET /api/v1/video-jobs/list?start_date=2026-01-07&end_date=2026-01-07
```

**Response:**
```json
{
  "total": 25,
  "filters_applied": {
    "start_date": "2026-01-07",
    "end_date": "2026-01-07"
  },
  "message": "Found 25 video job(s) with filters: from 2026-01-07, to 2026-01-07. Showing page 1 of 2."
}
```

---

### 5. **Combine Status + Date**
```bash
GET /api/v1/video-jobs/list?status=failed&start_date=2026-01-01&end_date=2026-01-07
```

**Response:**
```json
{
  "total": 12,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "status": "failed",
    "start_date": "2026-01-01",
    "end_date": "2026-01-07"
  },
  "message": "Found 12 video job(s) with filters: status='failed', from 2026-01-01, to 2026-01-07. Showing page 1 of 1.",
  "items": [...]
}
```

---

### 6. **Combine Status + Failed Stage**
```bash
GET /api/v1/video-jobs/list?status=failed&failed_stage=photo
```

**Response:**
```json
{
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "status": "failed",
    "failed_stage": "photo"
  },
  "message": "Found 5 video job(s) with filters: status='failed', failed_stage='photo'. Showing page 1 of 1.",
  "items": [...]
}
```

---

### 7. **Combine Status + Failed Stage + Date**
```bash
GET /api/v1/video-jobs/list?status=failed&failed_stage=lipsync&start_date=2026-01-07&end_date=2026-01-07
```

**Response:**
```json
{
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "status": "failed",
    "failed_stage": "lipsync",
    "start_date": "2026-01-07",
    "end_date": "2026-01-07"
  },
  "message": "Found 3 video job(s) with filters: status='failed', failed_stage='lipsync', from 2026-01-07, to 2026-01-07. Showing page 1 of 1.",
  "items": [...]
}
```

---

### 8. **Filter by User ID**
```bash
GET /api/v1/video-jobs/list?user_id=550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "total": 3,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "message": "Found 3 video job(s) with filters: user_id='550e8400-e29b-41d4-a716-446655440000'. Showing page 1 of 1.",
  "items": [...]
}
```

---

### 9. **Combine All Filters**
```bash
GET /api/v1/video-jobs/list?status=failed&failed_stage=photo&start_date=2026-01-01&end_date=2026-01-07&user_id=550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {
    "status": "failed",
    "failed_stage": "photo",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "start_date": "2026-01-01",
    "end_date": "2026-01-07"
  },
  "message": "Found 1 video job(s) with filters: status='failed', failed_stage='photo', user_id='550e8400-e29b-41d4-a716-446655440000', from 2026-01-01, to 2026-01-07. Showing page 1 of 1.",
  "items": [...]
}
```

---

## Pagination Examples

### **Page 1 (First 20 items)**
```bash
GET /api/v1/video-jobs/list?page=1&page_size=20
```

### **Page 2 (Next 20 items)**
```bash
GET /api/v1/video-jobs/list?page=2&page_size=20
```

### **Custom Page Size (50 items per page)**
```bash
GET /api/v1/video-jobs/list?page=1&page_size=50
```

### **Failed Jobs with Pagination**
```bash
GET /api/v1/video-jobs/list?status=failed&page=1&page_size=10
```

**Response:**
```json
{
  "total": 45,
  "page": 1,
  "page_size": 10,
  "total_pages": 5,
  "filters_applied": {
    "status": "failed"
  },
  "message": "Found 45 video job(s) with filters: status='failed'. Showing page 1 of 5.",
  "items": [10 items...]
}
```

---

## Common Use Cases

### **1. Monitor Today's Failed Jobs**
```bash
GET /api/v1/video-jobs/list?status=failed&start_date=2026-01-07&end_date=2026-01-07
```

### **2. Debug Photo Processing Issues**
```bash
GET /api/v1/video-jobs/list?status=failed&failed_stage=photo
```

### **3. Check Queued Jobs Waiting for Processing**
```bash
GET /api/v1/video-jobs/list?status=queued
```

### **4. Weekly Report (Last 7 Days)**
```bash
GET /api/v1/video-jobs/list?start_date=2026-01-01&end_date=2026-01-07
```

### **5. User's Job History**
```bash
GET /api/v1/video-jobs/list?user_id=USER_ID_HERE
```

### **6. Active Processing Jobs**
```bash
GET /api/v1/video-jobs/list?status=photo_processing
# OR
GET /api/v1/video-jobs/list?status=lipsync_processing
# OR
GET /api/v1/video-jobs/list?status=stitching
```

---

## Available Status Values
- `queued` - Waiting to be processed
- `photo_processing` - Currently processing photo
- `photo_done` - Photo processing complete
- `lipsync_processing` - Currently processing lipsync
- `lipsync_done` - Lipsync processing complete
- `stitching` - Currently stitching video
- `uploaded` - Video uploaded to storage
- `sent` - Video sent to user
- `failed` - Processing failed

## Available Failed Stage Values
- `photo` - Failed during photo processing
- `lipsync` - Failed during lipsync processing
- `stitch` - Failed during video stitching
- `delivery` - Failed during delivery/sending

---

## Response Fields Explanation

- **total**: Total number of jobs matching filters
- **page**: Current page number
- **page_size**: Number of items per page
- **total_pages**: Total pages available
- **filters_applied**: Object showing which filters were used
- **message**: Human-readable description of results
- **items**: Array of video job objects

---

## Tips

1. **Always check `total_pages`** to know if there are more results
2. **Use `filters_applied`** to confirm your filters were processed correctly
3. **Read `message`** for a quick summary of what was found
4. Jobs are **always sorted by `updated_at` DESC** (latest first)
5. **Maximum page_size is 100** items per page
6. All dates use **ISO 8601 format** (YYYY-MM-DD)
