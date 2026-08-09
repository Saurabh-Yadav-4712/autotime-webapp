# Software Requirements Specification
## for AutoTime WebApp

**Version 1.0 approved**
**Prepared by Antigravity**
**Date: August 7, 2026**

---

## Table of Contents
1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [External Interface Requirements](#3-external-interface-requirements)
4. [System Features](#4-system-features)
5. [Other Nonfunctional Requirements](#5-other-nonfunctional-requirements)
6. [Other Requirements](#6-other-requirements)
7. [Appendix A: Glossary](#appendix-a-glossary)

---

## 1. Introduction

### 1.1 Purpose
This Software Requirements Specification (SRS) document describes the software requirements for the **AutoTime WebApp**. It is intended to outline the complete feature set, functional capabilities, and non-functional requirements of the system. This document covers the entire scope of the AutoTime application, which serves as a centralized platform for institutes to manage, generate, and distribute academic timetables.

### 1.2 Document Conventions
- **Priorities**: High-level requirements and features are assumed to inherit priority from the core business needs. High-priority features are essential for system operation.
- **Formatting**: Bold text is used for emphasis and defining specific roles or UI elements.

### 1.3 Intended Audience and Reading Suggestions
This document is intended for:
- **Developers**: To understand the technical and functional constraints to maintain or extend the system.
- **Project Managers**: To track feature implementation and project scope.
- **Institute Administrators**: To understand the capabilities of the system they are deploying.
- **Testers**: To formulate test cases based on defined functional and non-functional requirements.

### 1.4 Product Scope
AutoTime WebApp is a web-based scheduling and timetable management system designed for educational institutions. The system automates the complex task of creating conflict-free schedules by considering constraints such as teacher availability, maximum teaching hours, and subject requirements. Additionally, it offers dedicated portals for administrators, teachers, and students. Key benefits include reduced administrative overhead, real-time schedule updates, automated proxy management when teachers are on leave, and seamless communication of schedules to students and faculty.

### 1.5 References
- Python/Flask Documentation
- SQLAlchemy Documentation
- Project Source Code (`app.py`, `requirements.txt`, Vercel configurations)

---

## 2. Overall Description

### 2.1 Product Perspective
AutoTime WebApp is a self-contained, web-based product. It operates as a monolithic Flask application with an integrated PostgreSQL database. It provides distinct views and functionalities based on role-based access control (Admin, Teacher, Student). The application is designed to be hosted on cloud platforms like Vercel, utilizing a relational database for persistent storage and an SMTP server for email-based communications (OTP).

### 2.2 Product Functions
- **Institute Registration & Configuration**: Secure sign-up with OTP email verification, dynamic timetable settings (lecture duration, breaks, start times).
- **Master Data Management**: CRUD operations for Courses, Teachers, and Subjects.
- **Automated Timetable Generation**: Algorithmic allocation of teachers to subjects in specific time slots without conflicts.
- **Leave & Proxy Management**: Teachers can apply for leave, prompting the system to assign proxy teachers automatically to their scheduled classes.
- **Export Functionality**: Ability to export generated timetables to Excel files (`.xlsx`).
- **Role-Based Dashboards**: Personalized views for Admins, Teachers (view personal schedule), and Students (view class schedule).
- **Account Settings**: Password management and profile updates via OTP.

### 2.3 User Classes and Characteristics
1. **Institute Admin (High Privilege)**: 
   - **Characteristics**: Responsible for configuring the institute, adding master data (teachers, courses, subjects), and generating the timetable.
   - **Technical Expertise**: Basic computer literacy.
2. **Teacher (Medium Privilege)**:
   - **Characteristics**: Uses the system to check their assigned classes and apply for leave.
   - **Technical Expertise**: Basic computer literacy.
3. **Student (Low Privilege)**:
   - **Characteristics**: Uses the system primarily in a read-only capacity to view their class timetable.
   - **Technical Expertise**: Basic computer literacy.

### 2.4 Operating Environment
- **Server-Side**: Python 3.x, Flask, SQLAlchemy, Werkzeug, openpyxl, psycopg2-binary.
- **Database**: PostgreSQL.
- **Deployment Platform**: Vercel (configured via `vercel.json`).
- **Client-Side**: Modern web browsers (Chrome, Firefox, Safari, Edge) supporting HTML5, CSS3, and JavaScript.

### 2.5 Design and Implementation Constraints
- **Language Requirements**: The backend must be written in Python using the Flask framework.
- **Database**: Must use PostgreSQL as defined by the SQLAlchemy configuration and `psycopg2-binary` dependency.
- **Authentication**: Custom session-based authentication using hashed passwords and email-based OTPs, rather than external OAuth providers.
- **Hosting**: The architecture must remain compatible with Vercel serverless deployments.

### 2.6 User Documentation
- Tooltips and intuitive UI flows within the application.
- (To be developed) Admin manual for configuring dynamic time slots and managing master data.

### 2.7 Assumptions and Dependencies
- **SMTP Server**: An active SMTP server (e.g., Gmail) is required and properly configured in environment variables (`SMTP_EMAIL`, `SMTP_PASSWORD`) for OTP delivery.
- **Database Availability**: A persistent PostgreSQL connection (`DATABASE_URL`) must be available.
- **Data Integrity**: Admins are expected to input realistic constraints; impossible constraints (e.g., total required subject hours exceeding available school hours) may result in incomplete timetable generation.

---

## 3. External Interface Requirements

### 3.1 User Interfaces
- **Landing Page**: Promotional and directional page with login/registration links.
- **Dashboards**: Distinct dashboard layouts for Admin, Teacher, and Student portals.
- **Forms**: Clean, responsive forms for data entry (Courses, Teachers, Subjects) with client-side and server-side validation.
- **Timetable View**: Grid or tabular layout representing the weekly schedule, highlighting current/upcoming classes and proxies.

### 3.2 Hardware Interfaces
- No specific hardware interfaces required. The system is accessed via standard networked devices (PCs, tablets, smartphones).

### 3.3 Software Interfaces
- **PostgreSQL Database**: Interfaced via SQLAlchemy ORM for all data persistence, querying, and relationship management.
- **Email Service (SMTP)**: Interfaced via Python's built-in `smtplib` for dispatching OTPs and notifications.

### 3.4 Communications Interfaces
- **HTTP/HTTPS**: Standard web protocols for client-server communication. HTTPS is strictly enforced in the production environment (Vercel).

---

## 4. System Features

### 4.1 Authentication and Authorization
- **4.1.1 Description and Priority**: High priority. Secure access control ensuring users only see data and features relevant to their role.
- **4.1.2 Stimulus/Response Sequences**:
  - User attempts to log in -> System verifies credentials (hashed via Werkzeug) -> System establishes a session and redirects to the appropriate dashboard.
  - Admin registers -> System sends OTP to email -> Admin enters OTP -> System creates Institute account.
- **4.1.3 Functional Requirements**:
  - REQ-AUTH-1: The system must use Werkzeug's `generate_password_hash` and `check_password_hash` for password storage and verification.
  - REQ-AUTH-2: The system must send a 6-digit OTP via email for account registration and password resets.
  - REQ-AUTH-3: The system must maintain secure session states.

### 4.2 Timetable Generation Algorithm
- **4.2.1 Description and Priority**: High priority. The core logic that allocates subjects to time slots without teacher conflicts.
- **4.2.2 Stimulus/Response Sequences**:
  - Admin initiates generation -> System reads all active courses, subjects, and teacher constraints -> System produces a schedule -> System saves to the database.
- **4.2.3 Functional Requirements**:
  - REQ-GEN-1: The system must respect teacher availability (days available) and maximum weekly hours.
  - REQ-GEN-2: The system must prevent assigning the same teacher to two different classes at the same time.
  - REQ-GEN-3: The system must support dynamic time slots configured by the Admin (e.g., lecture duration, breaks).

### 4.3 Proxy and Leave Management
- **4.3.1 Description and Priority**: Medium priority. Allows teachers to report absences and the system to adapt.
- **4.3.2 Stimulus/Response Sequences**:
  - Teacher applies for leave -> System flags the teacher as unavailable for that day -> System automatically reassigns those periods to an available teacher -> Admin/Students view updated schedule.
- **4.3.3 Functional Requirements**:
  - REQ-PRX-1: The system must provide an interface for teachers to select a date for leave.
  - REQ-PRX-2: The system must automatically identify free teachers during the absent teacher's slots and assign a proxy.
  - REQ-PRX-3: The proxy assignment must be visually distinct (`is_proxy = True`) in the timetable view.

### 4.4 Data Export
- **4.4.1 Description and Priority**: Low priority. Ability to download the schedule offline.
- **4.4.2 Stimulus/Response Sequences**:
  - User clicks Export -> System queries timetable data -> System generates `.xlsx` using `openpyxl` -> System streams file to the client.
- **4.4.3 Functional Requirements**:
  - REQ-EXP-1: The system must generate an Excel file with proper formatting (fonts, alignment, borders).

---

## 5. Other Nonfunctional Requirements

### 5.1 Performance Requirements
- The timetable generation algorithm must execute within an acceptable timeframe (typically < 10 seconds) for standard-sized institutes.
- Page load times should be optimized for quick access, especially for the Student Timetable view.

### 5.2 Safety Requirements
- As a scheduling application, there are no immediate physical safety requirements. However, data loss prevention (via robust database backups) is essential so institutes do not lose their master data.

### 5.3 Security Requirements
- **Passwords**: Never stored in plain text.
- **Environment Variables**: Sensitive data (`DATABASE_URL`, `SMTP_EMAIL`, `SMTP_PASSWORD`, `SECRET_KEY`) must be loaded from secure environment variables.
- **Session Protection**: Flask `SECRET_KEY` must be utilized to cryptographically sign session cookies.

### 5.4 Software Quality Attributes
- **Usability**: The dashboard interfaces must be intuitive enough for non-technical school administrators to configure the system without extensive training.
- **Maintainability**: The codebase utilizes SQLAlchemy ORM, abstracting raw SQL and making schema changes manageable.
- **Adaptability**: Dynamic time slot configurations allow the software to adapt to various school scheduling models (different lecture durations, varying break times).

### 5.5 Business Rules
- A Teacher cannot be assigned to more than one subject at the same time.
- A Teacher cannot exceed their predefined `max_hours`.
- An Institute is uniquely identified by its `institute_code`, which isolates data between different schools using the platform.

---

## 6. Other Requirements
- **Database Schema**: Must strictly adhere to the defined ORM models (`Institute`, `Teacher`, `Course`, `Subject`, `Timetable`, `Settings`, `Student`).
- **Cloud Compatibility**: File structures and routing must align with Vercel's serverless build processes as defined in `vercel.json`.

---

## Appendix A: Glossary
- **OTP**: One-Time Password. Used for verifying email addresses and authorizing sensitive actions.
- **Proxy**: A temporary teacher assigned to a class when the primary teacher is on leave.
- **ORM**: Object-Relational Mapping (e.g., SQLAlchemy). A technique that lets you query and manipulate data from a database using an object-oriented paradigm.
- **Institute Code**: A unique alphanumeric identifier generated by the system to isolate and relate all records pertaining to a specific institution.

---

## Appendix B: Analysis Models
- *(To be developed)* Entity-Relationship Diagram outlining the relationships between Institute -> Courses -> Subjects -> Timetable, and Teachers.

## Appendix C: To Be Determined List
1. Finalization of the exact UI/UX style guide.
2. Specific rate-limiting rules for OTP generation to prevent email spam.
3. Maximum threshold for Institute scaling (e.g., maximum concurrent teachers/courses per institute) to ensure optimal generation algorithm performance.
