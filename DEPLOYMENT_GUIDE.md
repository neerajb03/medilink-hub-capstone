# MediLink Hub — Deployment Guide

This guide provides step-by-step instructions on how to deploy the MediLink Hub production architecture from any laptop configured with Terraform and the AWS CLI.

## 📋 Prerequisites

Before you begin, ensure the following are installed and configured on your deployment machine:
1.  **AWS CLI**: Installed and configured (`aws configure`) with an IAM user that has Administrator access to provision resources.
2.  **Terraform**: Installed (version 1.5.0 or later).
3.  **Git**: Installed.

---

## 🛠️ Step 1: Clone the Repository

Open your terminal and clone the repository:

```bash
git clone https://github.com/neerajb03/medilink-hub.git
cd medilink-hub
```

---

## 📝 Step 2: Configure Pre-Deployment Variables

Before running Terraform, you should update a few placeholder email addresses so that you actually receive the system notifications.

1.  **Appointment Notifications Email**:
    *   Open `terraform/sns.tf`
    *   Find the `endpoint = "notifications@medilink.com"` line.
    *   Change `"notifications@medilink.com"` to your actual email address.

2.  **Operational Alarms Email**:
    *   Open `terraform/cloudwatch.tf`
    *   Find the `endpoint = "ops@medilink.com"` line.
    *   Change `"ops@medilink.com"` to your actual email address.

*(Note: There are **no hardcoded API keys or database passwords** in this repository. All sensitive credentials are dynamically generated or managed securely via AWS Secrets Manager.)*

---

## 🚀 Step 3: Deploy Infrastructure via Terraform

Navigate to the terraform directory and execute the deployment:

```bash
cd terraform

# Initialize the working directory and download AWS provider plugins
terraform init

# Validate the syntax of the configuration files
terraform validate

# Review the execution plan to see exactly what AWS resources will be created
terraform plan

# Apply the changes and build the infrastructure (Type 'yes' when prompted)
terraform apply
```

Deployment will take approximately **10-15 minutes** (primarily waiting for the RDS database and EC2 Auto Scaling Group to spin up).

---

## 🔐 Step 4: Post-Deployment Configuration

Once `terraform apply` completes successfully, there are two important manual steps you must perform in the AWS Console.

### 1. Update the Hugging Face AI API Key
Terraform created an AWS Secret for the AI symptom checker, but it populated it with a dummy placeholder. You must update it with a real key for the chatbot to work.

1.  Log into the AWS Management Console.
2.  Navigate to **Secrets Manager**.
3.  Click on the secret named `medilink/production/hf-api-key`.
4.  Click **Retrieve secret value** -> **Edit**.
5.  Replace the placeholder text `REPLACE_ME_MANUALLY_IN_CONSOLE` with your actual Hugging Face API Token (starting with `hf_...`).
6.  Click **Save**. The microservice will automatically fetch the new key on its next request.

### 2. Confirm SNS Email Subscriptions
AWS requires you to explicitly opt-in to receive automated emails.
1.  Check the inbox of the email address(es) you provided in Step 2.
2.  You will receive two emails from "AWS Notifications".
3.  Click the **Confirm subscription** link in both emails.

---

## 🌐 Step 5: Access the Application

At the end of the `terraform apply` run, Terraform will output several important values to your terminal. 

Look for `external_alb_dns`. This is the public URL of your Application Load Balancer. You can use this URL to interact with the MediLink API endpoints from tools like Postman or your frontend application.
