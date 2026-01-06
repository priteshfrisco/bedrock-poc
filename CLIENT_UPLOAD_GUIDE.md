# Client File Upload Guide

## 🎯 How Clients Can Upload Files

### **Option 1: AWS Console (Easiest - No Technical Skills Needed)**

**Steps:**
1. Go to AWS Console: https://console.aws.amazon.com/s3/
2. Log in with your credentials
3. Find bucket: `bedrock-ai-data-enrichment-data-XXXXX`
4. Click on `input/` folder
5. Click **"Upload"** button
6. Drag & drop your `uncoded_*.csv` file OR click "Add files"
7. Click **"Upload"**
8. ✅ Done! Processing starts automatically
9. Check email for completion notification (5-30 minutes later)

**Requirements:**
- File must start with `uncoded_` (e.g., `uncoded_january_2026.csv`)
- CSV format
- Max 2 files per month recommended

---

### **Option 2: AWS CLI (For Technical Users)**

```bash
# One-time setup
aws configure --profile client-prod
# Enter: Access Key, Secret Key, Region

# Upload file
aws s3 cp uncoded_products.csv \
  s3://bedrock-ai-data-enrichment-data-XXXXX/input/ \
  --profile client-prod

# Check status
aws s3 ls s3://bedrock-ai-data-enrichment-data-XXXXX/output/ \
  --recursive --profile client-prod
```

---

### **Option 3: Pre-Signed Upload URL (Most Secure)**

**For clients without AWS credentials:**

Generate a temporary upload URL (valid 1 hour):
```bash
aws s3 presign s3://BUCKET/input/uncoded_file.csv \
  --expires-in 3600 \
  --profile admin
```

Send this URL to client - they can upload via:
- Browser: Paste URL, file uploads automatically
- cURL: `curl -X PUT --upload-file uncoded_file.csv "PRESIGNED_URL"`

---

### **Option 4: Custom Upload Portal (Future Enhancement)**

**Simple web interface:**
- Login page
- Drag & drop file upload
- Real-time progress
- Email notification on completion

**Tech stack:**
- Frontend: React/Next.js hosted on S3/CloudFront
- Backend: API Gateway + Lambda
- Auth: Cognito or custom

**Estimated effort:** 2-3 days development

---

## 🔐 Security Considerations

### **Recommended Approach: IAM User per Client**

```bash
# Create IAM user for client
aws iam create-user --user-name client-acme-uploader

# Attach policy (upload to input only)
aws iam put-user-policy --user-name client-acme-uploader \
  --policy-name S3InputUpload \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::BUCKET/input/uncoded_*"
    }]
  }'

# Create access keys
aws iam create-access-key --user-name client-acme-uploader
```

Client gets:
- Access Key ID
- Secret Access Key
- Can ONLY upload to `input/` folder
- Can ONLY upload files starting with `uncoded_`

---

## 📊 Monitoring Client Uploads

**CloudWatch Alarm for uploads:**
```hcl
resource "aws_cloudwatch_metric_alarm" "file_upload" {
  alarm_name          = "s3-file-uploaded"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "NumberOfObjects"
  namespace           = "AWS/S3"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_actions       = [aws_sns_topic.notifications.arn]
}
```

---

## 🎯 RECOMMENDED FOR YOUR USE CASE

**For 1-2 files/month:**
→ **Option 1 (AWS Console)** is best!
- Simple, no setup needed
- Client already has AWS account access
- Built-in validation and security

**For frequent uploads or multiple clients:**
→ **Option 4 (Custom Portal)** 
- Better UX
- No AWS knowledge needed
- Easier to support

**Current setup:**
→ You have **Option 1** ready to use right now! ✅

