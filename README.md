# ReliefLink

## Disaster Relief Resource Distribution and Management System

ReliefLink is a database-driven Disaster Relief Resource Distribution and Management System designed to support the organized management and distribution of emergency resources during disasters.

The system provides a centralized platform for disaster management officers, departmental staff, donors, affected users, camps, warehouses, and helpline personnel. It manages disaster information, affected areas, relief camps, resources, donations, requests, warehouse stock, logistics, shipments, staff, helplines, local contacts, messages, call records, and system activity.

The project is developed as a desktop application using Python Tkinter with PostgreSQL as the relational database management system.

---

## Project Objectives

The main objectives of ReliefLink are:

- Centralize disaster relief information and resources.
- Manage disasters, regions, affected areas, camps, warehouses, and resources.
- Allow administrators to manage staff and departmental access.
- Allow users to register, request relief supplies, track requests, and make donations.
- Manage warehouse inventory and resource allocation.
- Support logistics and shipment management.
- Provide disaster-related helpline and local contact information.
- Maintain communication through database-backed messages.
- Maintain call records for helpline operations.
- Provide activity and security logging.
- Enforce role-based and department-based authorization.
- Maintain data integrity using PostgreSQL constraints, triggers, transactions, and locking.
- Provide reports and database views for management and analysis.

---

## Key Features

### 1. Role-Based Access Control

ReliefLink provides different access levels based on user roles.

#### Administrator

The Administrator represents the Disaster Management Officer and has complete system access.

The Administrator can:

- Configure the first administrator account.
- Manage disasters.
- Manage places and regions.
- Manage affected areas.
- Manage relief camps.
- Manage warehouses.
- Manage resources.
- Manage helplines.
- Manage local emergency contacts.
- Create and manage staff accounts.
- Assign staff to departments.
- Enable or disable staff accounts.
- Reset staff credentials.
- View system activity logs.
- Access reports and management information.

#### Staff

Staff accounts are created by the Administrator.

Staff members are assigned to specific departments:

- Logistics
- Warehouse
- Camp Relief
- Donations

Staff members can access functionality related to their assigned department.

Common communication facilities such as Messages and Call Log are available to authorized staff.

#### Normal User

Normal users can:

- Register an account.
- Log in.
- Request disaster relief assistance.
- Select appropriate places and camps.
- Request available supplies.
- Track their own requests.
- Make donations.
- Access relevant public disaster and helpline information.
- Communicate with authorized staff through Messages.

Normal users cannot access administrative information, other users' private information, exact warehouse stock information, staff records, or system activity logs.

#### Helpline / Urgent Help

The helpline interface can be accessed without logging in.

It provides emergency contact information and supports urgent relief assistance workflows.

If life is in immediate danger, users are instructed to contact emergency services first.

---

## Authentication and Security

ReliefLink implements database-backed authentication and security mechanisms.

Security features include:

- Password hashing using PostgreSQL `pgcrypto`.
- Security PIN hashing.
- Recovery key hashing.
- Password complexity validation.
- Six-digit security PIN validation.
- Account lockout after repeated failed login attempts.
- Temporary account locking.
- Login success and failure logging.
- Password reset using recovery credentials.
- Staff first-login credential change.
- Disabled account protection.
- Automatic session timeout after inactivity.
- Parameterized SQL queries.
- Transaction-based database operations.
- Row-level locking using `SELECT ... FOR UPDATE`.
- Role-based authorization.
- Department-based authorization.

Database credentials are supplied through environment variables rather than being stored directly in application source code.

---

## Disaster Management

Administrators can create and manage disaster records containing information such as:

- Disaster name
- Disaster type
- Severity
- Status
- Date
- Description

The system supports multiple disasters and allows disasters to affect multiple regions or affected areas.

---

## Places and Affected Areas

The system maintains geographical information required for disaster management.

Administrators can create:

- Regions
- Districts
- Places
- Affected areas

A disaster can be associated with multiple affected areas, and an affected area can be associated with the appropriate disaster and geographical location.

---

## Relief Camps

Administrators can create and manage relief camps.

Camp information includes:

- Camp name
- Place
- Associated disaster
- Population
- Status

Camps can request relief supplies based on their requirements.

---

## Warehouse and Resource Management

The Warehouse department manages disaster relief resources and inventory.

The system supports:

- Resource management.
- Warehouse stock management.
- Receiving donations.
- Stock availability.
- Low-stock monitoring.
- Resource allocation.
- Stock updates during shipment processing.

Database transactions and row-level locking are used for operations where concurrent access could affect stock consistency.

---

## Donations

The Donations module allows users and donors to contribute relief supplies.

Donation information can be maintained along with:

- Donor information
- Donation details
- Resource information
- Quantity
- Warehouse receipt information
- Donation history

Donated supplies can subsequently become part of warehouse inventory.

---

## Relief Requests

Users and camps can submit relief requests.

The request workflow includes:

1. Select a place.
2. Select a relief camp.
3. Select required supplies.
4. Review the request.
5. Submit the request.
6. Track request status.

Urgent assistance follows the same structured request workflow while being identified as an urgent requirement.

---

## Logistics and Shipment Management

The Logistics department handles the movement of relief resources from warehouses to camps.

The workflow includes:

1. Review pending requests.
2. Select the appropriate warehouse.
3. Select a vehicle.
4. Select a driver.
5. Confirm the shipment.
6. Deduct the allocated quantity from warehouse stock.
7. Track shipment progress.
8. Update delivery status.

The system is designed to maintain stock consistency during shipment processing.

---

## Helpline Management

ReliefLink provides multiple levels of emergency contact information:

- National
- State
- District
- Local
- Camp

Administrators can add, edit, enable, and disable helpline records.

The system also supports additional local emergency contacts associated with affected areas.

Local contacts can represent:

- Individuals
- Groups
- Community organizations
- Local relief teams

Multiple contacts can be associated with the same affected area.

---

## Messages

ReliefLink includes a database-backed messaging system.

The messaging workflow uses:

- Conversations
- Messages

When a user sends their first message, a conversation is created and an automatic response is generated:

> We received your message. A staff member will reply soon.

Messages are stored in the database and can be refreshed to retrieve the latest information.

Messages are not implemented as a real-time messaging service.

---

## Call Log

Authorized administrators and staff can maintain call records for helpline operations.

Call records include information such as:

- Caller name
- Caller phone
- Region
- Requirement
- Outcome
- Date and time
- Staff member who logged the call

This provides a structured record of emergency communication handled through the system.

---

## Database Design

PostgreSQL is used as the database management system.

The database design uses relational principles and includes appropriate:

- Primary keys
- Foreign keys
- Unique constraints
- Check constraints
- Not-null constraints
- Referential integrity
- Indexes
- Triggers
- Views
- Stored procedures/functions
- Transactions
- Row-level locking

The database uses PostgreSQL `pgcrypto` for secure credential hashing.

---

## Database Components

The project contains separate SQL files for major database components.

```text
schema.sql
data.sql
triggers.sql
views.sql
procedures.sql
indexes.sql
