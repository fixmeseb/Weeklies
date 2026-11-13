# Architecture (Overview)

- **Framework**: Flask  
- **Entrypoint**: Flask_app.py  
- **Database**: SQLite (`CSC510_DB.db`)
- **Database helpers**: sqlQueries.py (use only provided helpers)  
- **Templates / Static**: templates/, static/  
- **Meal planning**: menu_generation.py (planner), plan_rules.py (shared rules), variety.py (variety score), meal_tags.py (tags)

This document intentionally focuses on what's present today.

---

## Database Schema

The application uses SQLite with 5 main tables. Current data: 103 users, 19 restaurants, 269 menu items, 17 orders, and 50 reviews.

### 1. User Table

Stores customer account information, preferences, and AI-generated meal plans.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `usr_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT, UNIQUE, NOT NULL | Unique user identifier |
| `first_name` | TEXT | NOT NULL | User's first name |
| `last_name` | TEXT | NOT NULL | User's last name |
| `email` | TEXT | UNIQUE, NOT NULL | User's email (used for login) |
| `phone` | TEXT | UNIQUE, NOT NULL | User's phone number |
| `password_HS` | TEXT | NOT NULL | Hashed password (scrypt format) |
| `wallet` | INTEGER | NOT NULL | User's wallet balance in **cents** |
| `preferences` | TEXT | NULL | Comma-separated food preferences (e.g., "vegetarian, spicy") |
| `allergies` | TEXT | NULL | Comma-separated allergens to avoid |
| `generated_menu` | TEXT | NULL | Serialized AI-generated meal plan: `[YYYY-MM-DD,itm_id,meal_number]` format |

**Notes:**
- Wallet is stored in **cents** (e.g., 7816 = $78.16)
- `generated_menu` format: `[2025-11-15,42,1],[2025-11-15,58,2]` where meal_number is 1=breakfast, 2=lunch, 3=dinner
- Password uses scrypt hashing: `scrypt:32768:8:1$salt$hash`

**Sample Data:**
```
usr_id: 1
name: Loralyn Kernermann
email: lkernermann0@rambler.ru
wallet: 7816 (= $78.16)
preferences: "adipiscing"
allergies: (empty)
```

---

### 2. Restaurant Table

Stores restaurant information including authentication credentials and operating hours.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rtr_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT, UNIQUE, NOT NULL | Unique restaurant identifier |
| `name` | TEXT | NOT NULL | Restaurant name |
| `description` | TEXT | NULL | Restaurant description/bio |
| `phone` | TEXT | UNIQUE, NOT NULL | Contact phone number |
| `email` | TEXT | UNIQUE, NOT NULL | Restaurant email (for login) |
| `password_HS` | TEXT | NOT NULL | Hashed password (scrypt format) |
| `address` | TEXT | NOT NULL | Street address |
| `city` | TEXT | NOT NULL | City name |
| `state` | TEXT | NOT NULL | State abbreviation |
| `zip` | INTEGER | NOT NULL | ZIP code |
| `hours` | TEXT | NULL | JSON object with operating hours by day |
| `status` | TEXT | NULL | Restaurant status (e.g., "Open", "Closed") |

**Notes:**
- `hours` is a JSON string with format:
  ```json
  {
    "Mon": [start_time, end_time],
    "Tue": [1700, 2100],
    ...
  }
  ```
  - Times in 24-hour HHMM format (e.g., 1700 = 5:00 PM)
  - Empty array `[]` means closed that day
- `password_HS` enables restaurant owner login (**not currently implemented in UI**)
- `status` values observed: "Open", "Closed"

**Sample Data:**
```
rtr_id: 1
name: Bida Manda
hours: {"Mon": [], "Tue": [1700, 2100], "Wed": [1700, 2100], ...}
status: Open
```

---

### 3. MenuItem Table

Stores individual food items offered by restaurants.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `itm_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT, UNIQUE, NOT NULL | Unique item identifier |
| `rtr_id` | INTEGER | NOT NULL, FOREIGN KEY → Restaurant(rtr_id) | Restaurant that offers this item |
| `name` | TEXT | NOT NULL | Item name |
| `description` | TEXT | NULL | Item description |
| `price` | INTEGER | NOT NULL | Price in **cents** |
| `calories` | INTEGER | NOT NULL | Calorie count |
| `instock` | INTEGER | NOT NULL | Boolean: 1 = in stock, 0 = out of stock |
| `restock` | TEXT | NULL | Restock date/info (format not strictly defined) |
| `allergens` | TEXT | NULL | Comma-separated list of allergens |

**Notes:**
- Price is stored in **cents** (e.g., 1650 = $16.50)
- `instock` is used as boolean: 1 (true) or 0 (false)
- Common allergens: "Gluten", "Soy", "Dairy", "Nuts", "Sesame", "Shellfish", etc.

**Sample Data:**
```
itm_id: 1
rtr_id: 1 (Bida Manda)
name: Laotian Beef Stir Fry
price: 1650 (= $16.50)
calories: 450
instock: 1
allergens: "Gluten, Soy"
```

---

### 4. Order Table

Stores customer orders with detailed JSON information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `ord_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT, UNIQUE, NOT NULL | Unique order identifier |
| `rtr_id` | INTEGER | NOT NULL, FOREIGN KEY → Restaurant(rtr_id) | Restaurant fulfilling the order |
| `usr_id` | INTEGER | NOT NULL, FOREIGN KEY → User(usr_id) | Customer who placed the order |
| `details` | TEXT | NOT NULL | JSON object with complete order information |
| `status` | TEXT | NOT NULL | Current order status |

**Notes:**
- `status` values observed: "Ordered", "Accepted", "Preparing", "Ready", "Delivered", "Cancelled"
- **Current Implementation Gap**: Orders are created with status "Ordered" but **never updated** (no restaurant dashboard exists)
- `details` is a JSON string with structure:
  ```json
  {
    "placed_at": "2025-10-18T18:22:00-04:00",
    "restaurant_id": 2,
    "items": [
      {
        "itm_id": 25,
        "name": "Margherita Pizza",
        "qty": 1,
        "unit_price": 16.00,
        "line_total": 16.00,
        "notes": "Extra cheese"
      }
    ],
    "charges": {
      "subtotal": 34.00,
      "tax": 2.47,
      "delivery_fee": 3.99,
      "service_fee": 1.49,
      "tip": 5.00,
      "total": 46.95
    },
    "delivery_type": "delivery",  // or "pickup"
    "eta_minutes": 40,
    "date": "2025-11-15",
    "meal": 3  // 1=breakfast, 2=lunch, 3=dinner
  }
  ```

**Sample Data:**
```
ord_id: 125
rtr_id: 2 (Poole'side Pies)
usr_id: 101
status: Delivered
details: {JSON with 2 pizza items, total $46.95}
```

---

### 5. Review Table

Stores user reviews for restaurants.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `rev_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT, UNIQUE, NOT NULL | Unique review identifier |
| `rtr_id` | INTEGER | NOT NULL, FOREIGN KEY → Restaurant(rtr_id) | Restaurant being reviewed |
| `usr_id` | INTEGER | NOT NULL, FOREIGN KEY → User(usr_id) | User who wrote the review |
| `title` | TEXT | NULL | Review title/headline |
| `rating` | INTEGER | NOT NULL | Rating value (typically 1-5 stars) |
| `description` | TEXT | NULL | Review text content |

**Notes:**
- `rating` appears to use 1-5 scale
- Review functionality exists in schema but **UI implementation status unknown**

**Sample Data:**
```
rev_id: 1
rtr_id: 17
usr_id: 24
title: "Amazing Pizza!"
rating: 5
description: "Best pizza in Raleigh. Crust was perfectly crispy..."
```

---

## Data Relationships

```
User (usr_id)
  ├─→ Order (usr_id)           [One user → Many orders]
  └─→ Review (usr_id)          [One user → Many reviews]

Restaurant (rtr_id)
  ├─→ MenuItem (rtr_id)        [One restaurant → Many menu items]
  ├─→ Order (rtr_id)           [One restaurant → Many orders]
  └─→ Review (rtr_id)          [One restaurant → Many reviews]

MenuItem (itm_id)
  └─→ Referenced in Order.details JSON (not FK)

Order (ord_id)
  └─→ No child tables
```

---

## Current Implementation Status

### ✅ Fully Implemented
- User registration, login, logout, profile management
- Restaurant and menu item browsing
- Order placement (creates orders with status "Ordered")
- Order history viewing (users can see their past orders)
- PDF receipt generation
- Calendar-based menu display (reads `generated_menu` from User table)
- Wallet balance tracking

### ⚠️ Partially Implemented
- **Restaurant Authentication**: Table has `password_HS` field but **no login system**
- **Review System**: Table exists but UI implementation unclear

### ❌ Not Implemented
- **Order Status Updates**: Orders remain "Ordered" forever; no workflow for Accepted → Preparing → Ready → Delivered
- **Restaurant/Admin Dashboard**: No way for restaurants to view or manage orders
- **Order Status Transitions**: No routes to update order status
- **Real-time Order Management**: No interface for restaurant owners

---

## Potential Extensions

Based on the schema analysis, these features are database-ready but need implementation:

1. **Restaurant Dashboard**
   - Login system using `Restaurant.email` and `Restaurant.password_HS`
   - View incoming orders filtered by `rtr_id`
   - Update order status through workflow
   - Manage menu items (add/edit/disable items)

3. **Review System**
   - UI for users to leave reviews after order delivery
   - Display reviews on restaurant pages
   - Average rating calculation

4. **Enhanced Order Management**
   - Order status tracking for customers
   - Estimated delivery time updates
   - Order cancellation (by user or restaurant)
   - Refund processing (update `User.wallet`)

5. **Inventory Management**
   - Update `MenuItem.instock` when items sell out
   - Set `MenuItem.restock` dates
   - Automatic menu filtering based on stock

---

## Database Access Patterns

All database operations **must** use the helper functions in `sqlQueries.py`:
- `create_connection(db_path)` - Open database connection
- `close_connection(conn)` - Close database connection
- `fetch_one(conn, query, params)` - Fetch single row
- `fetch_all(conn, query, params)` - Fetch multiple rows
- `execute_query(conn, query, params)` - Execute INSERT/UPDATE/DELETE

**Never** use raw SQLite connections outside these helpers.
