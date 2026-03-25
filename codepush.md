# Code Push And Post-Push Checks

This guide explains how to:
- push code changes safely
- verify backend and frontend deployments
- run the minimum post-push checks for this MVP

## 1. Before You Push

Check what changed:

```bash
git status
```

Review the changed files and make sure you are only pushing the intended updates.

## 2. Commit The Change

Add only the files related to your change:

```bash
git add path/to/file1 path/to/file2
git commit -m "Short clear change summary"
```

If you intentionally want to push everything currently changed:

```bash
git add .
git commit -m "Describe the full update"
```

Recommended:
- prefer targeted `git add` instead of `git add .`
- keep commit messages short and specific

## 3. Push To GitHub

Push to the main branch:

```bash
git push origin main
```

If you are using a feature branch:

```bash
git push origin <branch-name>
```

## 4. What Happens After Push

For backend changes:
- GitHub Actions builds the Lambda container image
- the new image is published to ECR
- Lambda must be updated to use the new image tag

For frontend changes:
- build the correct frontend locally
- sync the generated `dist` bundle to the frontend S3 bucket

Important:
- the main hosted site is deployed from `frontend`
- the `/v2/` site is deployed from `demo-ui-design`
- pushing to git does not make frontend changes live by itself
- frontend changes are live only after the matching `dist` folder is synced to S3
- use the attached HTC logo asset only
- main frontend logo asset path: `frontend/public/htc_global_services_20260326.PNG`
- v2 frontend logo asset path: `demo-ui-design/public/htc_global_services_20260326.PNG`

## 5. Check GitHub Actions

Open GitHub:
- go to `Actions`
- open the latest workflow run
- confirm the workflow completed successfully

Important:
- the VS Code GitHub Actions extension is optional
- workflows run on GitHub even if that extension is not installed

## 6. Backend Post-Push Checks

### 6.1 Confirm The New Image Exists In ECR

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
& $py -m awscli ecr describe-images `
  --repository-name rag-api `
  --region ap-south-1 `
  --query "sort_by(imageDetails,& imagePushedAt)[-8:].[imageTags,imagePushedAt]" `
  --output json
```

Look for the latest commit hash as an image tag.

### 6.2 Update Lambda To The New Image

Replace `<commit-tag>` with the actual image tag:

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
& $py -m awscli lambda update-function-code `
  --function-name rag-serverless-rag-api `
  --image-uri '989126025320.dkr.ecr.ap-south-1.amazonaws.com/rag-api:<commit-tag>' `
  --region ap-south-1
```

### 6.3 Verify Lambda Is Using The New Image

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
& $py -m awscli lambda get-function `
  --function-name rag-serverless-rag-api `
  --region ap-south-1 `
  --query "Code.ImageUri" `
  --output text
```

### 6.4 Verify Lambda Update Status

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
& $py -m awscli lambda get-function-configuration `
  --function-name rag-serverless-rag-api `
  --region ap-south-1 `
  --query "{State:State,LastUpdateStatus:LastUpdateStatus,LastModified:LastModified}" `
  --output json
```

Expected:
- `State: Active`
- `LastUpdateStatus: Successful`

### 6.5 Run Health Check

```powershell
Invoke-RestMethod -Uri 'https://gj67rokz4s7k42mrvbo6xxtl2a0scxia.lambda-url.ap-south-1.on.aws/health' -Method Get | ConvertTo-Json -Depth 6
```

Expected:

```json
{
  "status": "ok",
  "services": {
    "s3": "ok",
    "dynamodb": "ok",
    "bedrock": "ok"
  }
}
```

## 7. Frontend Post-Push Checks

### 7.1 Set Node Path

```powershell
$env:Path='C:\Users\dhairya.jindani\Downloads\npm code\node-v22.14.0-win-x64;'+$env:Path
```

### 7.2 Lint And Build

```powershell
npm run lint
npm run build
```

Run those from:

```text
frontend
```

### 7.2a If You Are Deploying The Main Frontend

Run those commands from:

```text
frontend
```

### 7.2b If You Are Deploying The V2 Frontend

Set Node path first:

```powershell
$env:Path='C:\Users\dhairya.jindani\Downloads\npm code\node-v22.14.0-win-x64;'+$env:Path
```

Then run:

```powershell
npm run build
```

Run that from:

```text
demo-ui-design
```

### 7.3 Deploy Frontend To S3

#### Main frontend deploy

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
$src='C:\Users\dhairya.jindani\Documents\AI-coe projects\Rag\frontend\dist'
& $py -m awscli s3 sync $src 's3://rag-serverless-frontend' --delete --exclude 'v2/*'
```

This updates the main site at the bucket root.

Important:
- keep `--exclude 'v2/*'` in the main frontend deploy command
- otherwise the root sync can delete the deployed `/v2` site assets

#### V2 frontend deploy

```powershell
$py='C:\Users\dhairya.jindani\Documents\AI-coe projects\Call Analyzer\.venv\Scripts\python.exe'
$src='C:\Users\dhairya.jindani\Documents\AI-coe projects\Rag\demo-ui-design\dist'
& $py -m awscli s3 sync $src 's3://rag-serverless-frontend/v2' --delete
```

This updates:

```text
http://rag-serverless-frontend.s3-website.ap-south-1.amazonaws.com/v2/index.html
```

Important:
- do not deploy `frontend/dist` to the `/v2` path
- do not assume `/v2` is rebuilt by the main frontend deploy
- if you changed `demo-ui-design`, you must explicitly sync `demo-ui-design/dist` to `s3://rag-serverless-frontend/v2`
- if you changed logo branding, rebuild and deploy both `frontend` and `demo-ui-design` when both experiences use the logo

Recommended deploy order when both changed:
1. deploy `frontend` to the bucket root with `--exclude 'v2/*'`
2. deploy `demo-ui-design` to `s3://rag-serverless-frontend/v2`

### 7.4 Browser Check

After frontend deploy:
- hard refresh the browser
- confirm new UI changes are visible
- if needed, open the hosted site directly

Recommended direct URLs:
- main site: `http://rag-serverless-frontend.s3-website.ap-south-1.amazonaws.com/`
- v2 site: `http://rag-serverless-frontend.s3-website.ap-south-1.amazonaws.com/v2/index.html`

## 8. Minimum Functional Smoke Test

Always test the exact feature you changed.

Also run 1 quick regression check nearby.

Examples:

### If Chat Changed
- sign in
- ask a normal question
- upload a document
- ask a RAG question
- verify citations

### If Upload Changed
- select a file
- upload it
- verify indexed documents count updates
- ask a question from the uploaded file

### If Analytics Changed
- open Analytics tab
- load dataset
- verify KPI cards
- run one analytics query

### If Agents Changed
- open Agents tab
- start a run
- verify sections render
- verify final report appears

### If Image Flow Changed
- attach an image
- ask a question from the screenshot
- verify answer comes from the image content

## 9. Recommended Post-Push Checklist

Use this every time:

- code pushed successfully
- correct branch pushed
- GitHub Actions workflow passed
- new ECR image exists
- Lambda updated to latest image
- Lambda status is `Successful`
- `/health` returns `ok`
- frontend built and deployed if needed
- changed feature works
- no obvious regression in nearby flow

## 10. Notes

- GitHub Actions editor extension is optional and not required for deployments
- backend code changes are not live until Lambda points to the new image
- frontend code changes are not live until the built assets are synced to S3
- `frontend` and `demo-ui-design` are separate deploy targets
- `frontend` deploys the main site
- `demo-ui-design` deploys the `/v2/` experience
- both UIs should use the shared HTC Global Services image asset, not generated text or alternate logo files
- if a change affects existing indexed data behavior, you may need to re-upload documents or rebuild data for the improvement to fully apply
