# Weeklies Use-Case Catalog

This catalog was derived from the behavior implemented in the Weeklies repository and informed by the broader ideas in `use_case.md`. It intentionally excludes unimplemented platform actors and capabilities such as drivers, payment processors, GPS delivery zones, promotions, substitutions, refunds, and support claims.

## UC01 — Register account

| Part | Specification |
|---|---|
| **Name** | Register account |
| **Primary actor** | Prospective customer |
| **Stakeholders & interests** | Customer—wants a secure identity and saved meal preferences. Weeklies—wants valid, unique customer records. |
| **Preconditions** | The actor is not signed in and can provide an unused email address. |
| **Trigger** | The actor chooses to create a customer account. |
| **Main success scenario** | 1. The actor provides their name, email, phone number, password, preferences, and allergies.<br>2. Weeklies validates the account information.<br>3. Weeklies creates the customer account with a protected password.<br>4. Weeklies directs the actor to sign in. |
| **Extensions** | 2a. First or last name is absent → Weeklies explains that both are required and preserves the entered information.<br>2b. Password and confirmation differ → Weeklies rejects the request and explains the mismatch.<br>2c. Password is shorter than the minimum → Weeklies rejects the request and states the minimum length.<br>2d. Phone number has an invalid format → Weeklies requests a valid phone number.<br>2e. Email is already registered → Weeklies reports the duplicate and does not create another account.<br>3a. Account storage fails → Weeklies reports that registration could not be completed. |
| **Postconditions** | A unique customer account exists and the actor can authenticate with the submitted credentials. |

## UC02 — Sign in as customer

| Part | Specification |
|---|---|
| **Name** | Sign in as customer |
| **Primary actor** | Registered customer |
| **Stakeholders & interests** | Customer—wants access to personal plans and orders. Weeklies—wants only authenticated customers to access private data. |
| **Preconditions** | A customer account exists and the actor is not signed in. |
| **Trigger** | The actor submits customer credentials. |
| **Main success scenario** | 1. The actor provides an email address and password.<br>2. Weeklies verifies the credentials.<br>3. Weeklies establishes a time-limited customer session.<br>4. Weeklies shows the customer's meal-plan calendar. |
| **Extensions** | 2a. The email is unknown → Weeklies reports invalid credentials.<br>2b. The password does not match → Weeklies reports invalid credentials.<br>3a. The session expires after inactivity → Weeklies requires the customer to sign in again. |
| **Postconditions** | A customer session identifies the actor and provides access to customer-only capabilities. |

## UC03 — Sign out as customer

| Part | Specification |
|---|---|
| **Name** | Sign out as customer |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants to prevent later users of the device from accessing private data. Weeklies—wants the session's customer identity removed. |
| **Preconditions** | The customer is signed in. |
| **Trigger** | The customer requests to sign out. |
| **Main success scenario** | 1. The customer requests sign-out.<br>2. Weeklies ends the active customer identity.<br>3. Weeklies returns the customer to the sign-in page. |
| **Extensions** | 1a. The customer cancels the sign-out confirmation → Weeklies leaves the session active.<br>2a. The session has already expired → Weeklies still returns the actor to sign-in. |
| **Postconditions** | Customer-only pages require authentication again. |

## UC04 — Update profile

| Part | Specification |
|---|---|
| **Name** | Update profile |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants accurate contact information and personalization inputs. Weeklies—wants a valid, uniquely identifiable account. Menu generator—needs current preferences and allergies. |
| **Preconditions** | The customer is signed in and their account still exists. |
| **Trigger** | The customer chooses to edit their profile. |
| **Main success scenario** | 1. Weeklies presents the customer's current profile information.<br>2. The customer revises their name, email, phone, preferences, or allergies.<br>3. Weeklies validates the revisions.<br>4. Weeklies saves the profile.<br>5. Weeklies refreshes the active session with the saved values.<br>6. Weeklies shows the updated profile. |
| **Extensions** | 1a. The session does not identify an account → Weeklies ends the session and requests sign-in.<br>3a. A required value is invalid → Weeklies explains the problem and does not save.<br>3b. The revised email belongs to another account → Weeklies rejects the duplicate email.<br>4a. The account disappears before saving → Weeklies ends the invalid session. |
| **Postconditions** | The stored profile and active customer session contain the same updated values. |

## UC05 — Change password

| Part | Specification |
|---|---|
| **Name** | Change password |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants control of account security. Weeklies—wants only the account holder to replace credentials. |
| **Preconditions** | The customer is signed in and knows the current password. |
| **Trigger** | The customer submits a password-change request. |
| **Main success scenario** | 1. The customer provides the current password, a new password, and confirmation.<br>2. Weeklies validates the new password and confirmation.<br>3. Weeklies verifies the current password.<br>4. Weeklies protects and stores the new password.<br>5. Weeklies confirms the change. |
| **Extensions** | 1a. Current password is absent → Weeklies requests it.<br>2a. New password is too short → Weeklies states the minimum length.<br>2b. New password and confirmation differ → Weeklies reports the mismatch.<br>2c. New password equals the current password → Weeklies requests a different password.<br>3a. Current password is incorrect → Weeklies rejects the change.<br>3b. The account no longer exists → Weeklies ends the session. |
| **Postconditions** | The old password no longer authenticates the customer and the new password does. |

## UC06 — Generate meal plan

| Part | Specification |
|---|---|
| **Name** | Generate meal plan |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants suitable meal suggestions for chosen dates and meal periods. Restaurants—want only available offerings recommended. Weeklies—wants suggestions constrained by hours, stock, and declared allergies. |
| **Preconditions** | The customer is signed in; restaurants and in-stock menu items exist; restaurant hours are available. |
| **Trigger** | The customer requests menu generation for a start date, meal periods, and number of days. |
| **Main success scenario** | 1. The customer specifies the planning period and meal periods.<br>2. Weeklies obtains the customer's preferences and allergies.<br>3. Weeklies identifies suitable items from open restaurants for each requested meal.<br>4. Weeklies selects one offered item for each unplanned date and meal period.<br>5. Weeklies adds the selections to the customer's existing plan.<br>6. Weeklies saves the expanded plan.<br>7. Weeklies shows the calendar containing the selections. |
| **Extensions** | 1a. No meal period is selected → Weeklies generates breakfast, lunch, and dinner.<br>1b. The date is invalid → Weeklies uses the current date.<br>1c. The requested duration is below one day → Weeklies uses one day.<br>1d. The requested duration exceeds fourteen days → Weeklies limits it to fourteen days.<br>3a. Restaurant hours are malformed → Weeklies treats the affected restaurant as closed.<br>3b. No item is eligible for a requested meal (closed restaurants, no suitable main, allergies, or diet) → Weeklies reports which rule left the meal empty and leaves the plan unchanged.<br>4a. Several items are eligible → Weeklies picks the combination that keeps each week's meals most varied (protein, cuisine, restaurant, cooking method and similar traits), preferring nearby meals to differ most.<br>5a. A date and meal period already has a selection → Weeklies retains it and continues with other requested periods. |
| **Postconditions** | The customer's plan contains at most one generated entry for each requested date/meal pair and persists for later sessions. |

## UC07 — View meal calendar

| Part | Specification |
|---|---|
| **Name** | View meal calendar |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants an understandable monthly plan and quick access to today's meals. Weeklies—wants stored selections resolved to current restaurant/menu information. |
| **Preconditions** | The customer is signed in. |
| **Trigger** | The customer opens the home page or selects a calendar month. |
| **Main success scenario** | 1. Weeklies loads the customer's saved meal-plan entries.<br>2. Weeklies resolves each referenced item and restaurant.<br>3. Weeklies arranges entries by date and meal period.<br>4. Weeklies shows the requested month and today's meals.<br>5. The customer reviews the plan. |
| **Extensions** | 1a. The customer has no plan → Weeklies shows an empty calendar.<br>1b. A legacy entry omits a meal period → Weeklies treats it as dinner.<br>1c. A stored entry is malformed → Weeklies ignores that entry.<br>2a. A referenced item no longer exists → Weeklies omits it from the displayed plan.<br>2b. The account no longer exists → Weeklies ends the session.<br>4a. No month is specified → Weeklies shows the current month. |
| **Postconditions** | The customer has seen a calendar representation of all resolvable plan entries for the requested month; no plan data is changed. |

## UC08 — Browse restaurants

| Part | Specification |
|---|---|
| **Name** | Browse restaurants |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants restaurant identity, location, hours, status, and offerings. Restaurants—want accurate business information displayed. |
| **Preconditions** | The customer is signed in and restaurant records exist. |
| **Trigger** | The customer opens the restaurant catalog. |
| **Main success scenario** | 1. Weeklies retrieves restaurant details.<br>2. Weeklies retrieves currently available menu items.<br>3. Weeklies associates each item with its restaurant.<br>4. Weeklies shows restaurants, their details, and their available items.<br>5. The customer examines a restaurant. |
| **Extensions** | 1a. No restaurants exist → Weeklies shows an empty catalog.<br>2a. A restaurant has no in-stock items → Weeklies shows the restaurant without orderable items.<br>2b. An item's stock state is unspecified → Weeklies treats the item as available.<br>4a. Address components are absent → Weeklies displays the available components without empty separators. |
| **Postconditions** | The customer has seen the current restaurant catalog; no order or profile data is changed. |

## UC09 — Browse available meals

| Part | Specification |
|---|---|
| **Name** | Browse available meals |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants prices, calories, allergens, and descriptions before ordering. Restaurants—want unavailable items excluded. |
| **Preconditions** | The customer is signed in and at least one restaurant has menu data. |
| **Trigger** | The customer opens the ordering catalog. |
| **Main success scenario** | 1. Weeklies retrieves restaurants and their available items.<br>2. Weeklies presents item descriptions, prices, calorie information, and allergens by restaurant.<br>3. The customer reviews the offerings.<br>4. The customer selects items for one restaurant. |
| **Extensions** | 1a. No available items exist → Weeklies presents an empty ordering state.<br>1b. An item's stock state is unspecified → Weeklies includes it as available.<br>2a. Optional nutrition or allergen information is absent → Weeklies presents the remaining item information. |
| **Postconditions** | The customer has selected zero or more items associated with a single restaurant; no server-side order yet exists. |

## UC10 — Build restaurant order

| Part | Specification |
|---|---|
| **Name** | Build restaurant order |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants correct quantities and preparation notes. Restaurant—wants an unambiguous order containing only its items. Weeklies—wants one restaurant per order. |
| **Preconditions** | The customer is viewing available menu items. |
| **Trigger** | The customer adds an item to an order. |
| **Main success scenario** | 1. The customer selects a restaurant item.<br>2. The customer specifies a quantity and optional notes.<br>3. Weeklies adds the selection to the pending order.<br>4. The customer repeats selection for additional items from the same restaurant.<br>5. Weeklies presents the pending items and estimated charges.<br>6. The customer approves the pending order for placement. |
| **Extensions** | 2a. Quantity is not positive → Weeklies uses a quantity of one.<br>3a. The item is already present → Weeklies updates its pending quantity.<br>4a. The customer selects an item from another restaurant → Weeklies requires a separate order or replacement of the current restaurant's items.<br>5a. The customer removes an item → Weeklies recalculates the pending order.<br>5b. The customer empties the order → Weeklies prevents placement. |
| **Postconditions** | A client-side pending order contains one or more items associated with one restaurant and is ready for placement. |

## UC11 — Place delivery order

| Part | Specification |
|---|---|
| **Name** | Place delivery order |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants the chosen food ordered with predictable charges. Restaurant—wants authoritative item details and a new actionable order. Weeklies—wants valid order ownership and totals. |
| **Preconditions** | The customer is signed in and has approved a non-empty, single-restaurant pending order. |
| **Trigger** | The customer requests delivery order placement. |
| **Main success scenario** | 1. The customer submits the restaurant, items, quantities, notes, tip, planned date, meal period, and delivery choice.<br>2. Weeklies verifies the restaurant and every item against the catalog.<br>3. Weeklies obtains authoritative item names and prices.<br>4. Weeklies calculates subtotal, tax, delivery fee, service fee, tip, and total.<br>5. Weeklies records one customer-owned order with status `Ordered`.<br>6. Weeklies returns the order identifier.<br>7. Weeklies makes the new order visible in customer history and the restaurant's incoming orders. |
| **Extensions** | 1a. Restaurant or item list is absent → Weeklies rejects the request as invalid.<br>1b. All item identifiers are invalid → Weeklies rejects the request.<br>2a. No submitted items exist → Weeklies reports that items were not found.<br>2b. A particular item does not exist → Weeklies identifies the missing item and does not create an order.<br>2c. An item belongs to another restaurant → Weeklies rejects the mixed-restaurant order.<br>4a. Delivery choice is unrecognized → Weeklies treats it as delivery.<br>4b. Quantity is not positive → Weeklies charges for one.<br>7a. Analytics recording fails → Weeklies preserves the placed order and continues without blocking the customer. |
| **Postconditions** | Exactly one `Ordered` order exists for the customer and restaurant with server-derived item prices and a $3.99 delivery fee. |

## UC12 — Place pickup order

| Part | Specification |
|---|---|
| **Name** | Place pickup order |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants to collect food without a delivery fee. Restaurant—wants pickup intent included with the order. Weeklies—wants the same item and ownership validation as delivery. |
| **Preconditions** | The customer is signed in and has approved a non-empty, single-restaurant pending order. |
| **Trigger** | The customer requests pickup order placement. |
| **Main success scenario** | 1. The customer submits the restaurant, items, quantities, notes, tip, planned date, meal period, and pickup choice.<br>2. Weeklies verifies the restaurant and every item against the catalog.<br>3. Weeklies obtains authoritative item names and prices.<br>4. Weeklies calculates subtotal, tax, service fee, tip, and total without a delivery fee.<br>5. Weeklies records one customer-owned order with status `Ordered` and pickup type.<br>6. Weeklies returns the order identifier.<br>7. Weeklies makes the order visible to the customer and restaurant. |
| **Extensions** | 1a. Required order content is absent → Weeklies rejects the request.<br>2a. An item is missing or belongs to another restaurant → Weeklies rejects the order and identifies the applicable error.<br>3a. The submitted price differs from the catalog → Weeklies uses the catalog price.<br>4a. Quantity is not positive → Weeklies charges for one.<br>7a. Analytics recording fails → Weeklies preserves the order and continues. |
| **Postconditions** | Exactly one `Ordered` pickup order exists with server-derived prices and a zero delivery fee. |

## UC13 — Track order history

| Part | Specification |
|---|---|
| **Name** | Track order history |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants current status, how far the order has progressed and what remains, item details, charges, and relevant follow-up actions. Restaurant—wants its status updates reflected accurately. |
| **Preconditions** | The customer is signed in. |
| **Trigger** | The customer opens their profile. |
| **Main success scenario** | 1. Weeklies retrieves orders owned by the customer.<br>2. Weeklies interprets each order's item, charge, scheduling, and fulfillment details.<br>3. Weeklies orders the history with newest orders first.<br>4. Weeklies shows each order's restaurant, contents, total, and current status, with its progress through the lifecycle (Ordered → Accepted → Preparing → Ready → Delivered): stages reached, the current stage, and stages still to come.<br>5. Weeklies presents the actions appropriate to each order. |
| **Extensions** | 1a. The customer has no orders → Weeklies shows an empty order history.<br>2a. An order contains malformed details → Weeklies shows safe fallback values for that order.<br>4a. An order references unavailable restaurant information → Weeklies displays the remaining order information.<br>4b. An order is cancelled → Weeklies marks it cancelled and shows the lifecycle as not completed, without claiming which stages were reached.<br>4c. An order's status is missing or outside the known lifecycle → Weeklies shows the stored value (or "Unknown") without a progress position and still displays the rest of the history.<br>5a. A delivered order has no review → Weeklies offers review submission.<br>5b. A delivered order already has a review → Weeklies offers review viewing. |
| **Postconditions** | The customer has seen the latest stored state of all owned orders; no order is changed. |

> **Project 2 extension (visible order progress).** Step 4's progress view and extensions 4b–4c were added in Project 2; previously only the current status word was shown, and `Accepted`/`Ready` had no visual treatment. Orders store only their current status, so progress is derived from it; recording *when* each stage was reached would need a status-history table and is future scope. Implemented in `proj2/order_progress.py` and `proj2/templates/profile.html`; tested in `proj2/sef26tests/test_uc13_order_progress.py` and `test_uc13_track_orders.py`.

## UC14 — Download order receipt

| Part | Specification |
|---|---|
| **Name** | Download order receipt |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants a portable record of an order and charges. Weeklies—must prevent disclosure of another customer's order. Restaurant—wants its identity and contact details represented accurately. |
| **Preconditions** | The customer is signed in and an order exists. |
| **Trigger** | The customer requests a receipt for an order. |
| **Main success scenario** | 1. Weeklies verifies that the order belongs to the customer.<br>2. Weeklies loads the order, customer, and restaurant details.<br>3. Weeklies formats items, charges, fulfillment type, date, and status into a receipt.<br>4. Weeklies returns the receipt as a PDF download. |
| **Extensions** | 1a. The order does not exist → Weeklies reports not found.<br>1b. The order belongs to another customer → Weeklies refuses access.<br>2a. Optional customer or restaurant fields are absent → Weeklies leaves those receipt fields blank.<br>2b. Order details are malformed → Weeklies produces a safe partial receipt.<br>3a. The order contains more items than one page → Weeklies continues the item list on additional pages.<br>3b. The order is cancelled → Weeklies visibly marks the receipt as cancelled. |
| **Postconditions** | The owning customer receives a PDF for the requested order; order data is unchanged. |

## UC15 — Submit order review

| Part | Specification |
|---|---|
| **Name** | Submit order review |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants to share feedback on a completed purchase. Restaurant—wants feedback tied to a real order. Other customers—want credible ratings. Weeklies—wants one valid review per delivered order. |
| **Preconditions** | The customer owns an order whose status is `Delivered`, and that order has no review. |
| **Trigger** | The customer chooses to review the delivered order. |
| **Main success scenario** | 1. Weeklies verifies order ownership and delivery status.<br>2. Weeklies presents the order summary.<br>3. The customer provides a rating from one through five and optional title and description.<br>4. Weeklies validates the rating.<br>5. Weeklies records the review against the customer, restaurant, and order.<br>6. Weeklies returns the customer to their profile. |
| **Extensions** | 1a. The order does not exist or belongs to another customer → Weeklies returns the customer to their profile.<br>1b. The order is not delivered → Weeklies returns the customer to their profile without accepting a review.<br>1c. A review already exists → Weeklies shows the existing review.<br>3a. No rating is provided → Weeklies requests a rating and preserves the review form.<br>4a. Rating is outside one through five or is not numeric → Weeklies reports an invalid rating. |
| **Postconditions** | Exactly one review exists for the delivered order and contributes to the restaurant's review statistics. |

## UC16 — View submitted review

| Part | Specification |
|---|---|
| **Name** | View submitted review |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants to confirm previously submitted feedback. Weeklies—must keep order-linked customer data scoped to its author. |
| **Preconditions** | The customer is signed in and has submitted a review for an owned order. |
| **Trigger** | The customer chooses to view the order's review. |
| **Main success scenario** | 1. Weeklies locates the review for the customer and order.<br>2. Weeklies obtains the associated restaurant name.<br>3. Weeklies shows the rating, title, description, date, restaurant, and order reference.<br>4. The customer reads the review. |
| **Extensions** | 1a. No matching review exists → Weeklies returns the customer to their profile.<br>1b. The review belongs to another customer → Weeklies does not disclose it and returns to profile. |
| **Postconditions** | The customer has viewed their review; no review data is changed. |

## UC17 — Browse restaurant reviews

| Part | Specification |
|---|---|
| **Name** | Browse restaurant reviews |
| **Primary actor** | Visitor |
| **Stakeholders & interests** | Visitor—wants evidence about restaurant quality. Review authors—want feedback attributed appropriately. Restaurant—wants fair aggregate and individual presentation. |
| **Preconditions** | A restaurant exists. Customer authentication is not required. |
| **Trigger** | The visitor requests the restaurant's reviews. |
| **Main success scenario** | 1. Weeklies identifies the restaurant.<br>2. Weeklies calculates its review count and average rating.<br>3. Weeklies obtains one page of recent reviews.<br>4. Weeklies shows review authors, dates, ratings, titles, and descriptions.<br>5. The visitor navigates the available pages. |
| **Extensions** | 1a. The restaurant does not exist → Weeklies reports not found.<br>2a. The restaurant has no reviews → Weeklies shows a zero-rating empty state.<br>3a. The visitor chooses highest rating → Weeklies sorts by rating descending, then recency.<br>3b. The visitor chooses lowest rating → Weeklies sorts by rating ascending, then recency.<br>3c. The visitor selects a rating from one through five → Weeklies includes only matching reviews.<br>3d. The rating filter is invalid → Weeklies ignores it.<br>3e. A review is highlighted → Weeklies emphasizes that review on the page. |
| **Postconditions** | The visitor has seen the requested public review page; stored reviews are unchanged. |

## UC18 — Sign in as restaurant owner

| Part | Specification |
|---|---|
| **Name** | Sign in as restaurant owner |
| **Primary actor** | Restaurant owner |
| **Stakeholders & interests** | Owner—wants access only to their restaurant's operations. Customers—want order and personal information protected from other restaurants. Weeklies—wants strict restaurant scoping. |
| **Preconditions** | The restaurant has an email address and protected password. |
| **Trigger** | The owner submits restaurant credentials. |
| **Main success scenario** | 1. The owner provides the restaurant email and password.<br>2. Weeklies verifies the credentials.<br>3. Weeklies establishes a time-limited restaurant session scoped to that restaurant.<br>4. Weeklies shows the restaurant dashboard. |
| **Extensions** | 2a. The email is unknown → Weeklies reports invalid credentials.<br>2b. The password does not match → Weeklies reports invalid credentials.<br>3a. The session expires → Weeklies requires restaurant authentication again. |
| **Postconditions** | An owner session identifies exactly one restaurant and enables restaurant-only capabilities. |

## UC19 — Sign out as restaurant owner

| Part | Specification |
|---|---|
| **Name** | Sign out as restaurant owner |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants operational and customer data protected after use. Weeklies—wants all restaurant-scope session values removed. |
| **Preconditions** | A restaurant-owner session is active. |
| **Trigger** | The owner requests sign-out. |
| **Main success scenario** | 1. The owner requests sign-out.<br>2. Weeklies clears the active restaurant identity and scope.<br>3. Weeklies shows the restaurant sign-in page. |
| **Extensions** | 2a. The session is already absent or expired → Weeklies still shows restaurant sign-in. |
| **Postconditions** | Restaurant-only pages and actions require authentication again. |

## UC20 — View restaurant dashboard

| Part | Specification |
|---|---|
| **Name** | View restaurant dashboard |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants a quick operational summary. Customers—want only their order's restaurant to see it. Weeklies—wants metrics scoped to the session restaurant. |
| **Preconditions** | The owner is authenticated for one restaurant. |
| **Trigger** | The owner opens the dashboard. |
| **Main success scenario** | 1. Weeklies identifies the session restaurant.<br>2. Weeklies counts that restaurant's orders by lifecycle status.<br>3. Weeklies calculates review count and average rating.<br>4. Weeklies shows the restaurant identity, operational counts, and review summary.<br>5. The owner chooses an operational module. |
| **Extensions** | 1a. Restaurant authentication is absent → Weeklies redirects to restaurant sign-in.<br>2a. No orders exist → Weeklies shows zero for every status.<br>3a. No reviews exist → Weeklies shows a zero-review state. |
| **Postconditions** | The owner has seen a summary containing only their restaurant's data; operational data is unchanged. |

## UC21 — Review restaurant orders

| Part | Specification |
|---|---|
| **Name** | Review restaurant orders |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants customer contact, item, charge, schedule, and fulfillment details grouped by action state. Customer—wants their order visible only to the correct restaurant. |
| **Preconditions** | The owner is authenticated for one restaurant. |
| **Trigger** | The owner opens order management. |
| **Main success scenario** | 1. Weeklies retrieves orders belonging to the session restaurant.<br>2. Weeklies associates each order with customer contact information.<br>3. Weeklies interprets item, charge, schedule, and fulfillment details.<br>4. Weeklies groups orders by status.<br>5. Weeklies shows newest orders and the actions valid for each group.<br>6. The owner reviews an order. |
| **Extensions** | 1a. No orders exist → Weeklies shows empty status groups.<br>3a. An order's details are malformed → Weeklies shows safe default details.<br>4a. An order has an unknown status → Weeklies places it in an `Other` group.<br>1b. Owner authentication is absent → Weeklies redirects to restaurant sign-in. |
| **Postconditions** | The owner has seen only their restaurant's orders; no status is changed. |

## UC22 — Accept order

| Part | Specification |
|---|---|
| **Name** | Accept order |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants to commit the restaurant to a fulfillable order. Customer—wants prompt confirmation. Weeklies—wants valid ownership and lifecycle ordering. |
| **Preconditions** | The owner is authenticated for the order's restaurant and the order status is `Ordered`. |
| **Trigger** | The owner chooses to accept the incoming order. |
| **Main success scenario** | 1. The owner requests acceptance.<br>2. Weeklies verifies the order and restaurant ownership.<br>3. Weeklies verifies that the order is awaiting a decision.<br>4. Weeklies changes the status to `Accepted`.<br>5. Weeklies updates restaurant analytics.<br>6. Weeklies confirms the new state. |
| **Extensions** | 2a. The order does not exist → Weeklies reports not found.<br>2b. The order belongs to another restaurant → Weeklies refuses access.<br>3a. The order is not `Ordered` → Weeklies rejects the transition.<br>5a. Analytics update fails → Weeklies keeps the accepted status and continues.<br>6a. The request expects a page response → Weeklies returns the owner to order management.<br>6b. The request expects an asynchronous response → Weeklies returns the new status. |
| **Postconditions** | The order status is `Accepted` and it is eligible to enter preparation. |

## UC23 — Reject order

| Part | Specification |
|---|---|
| **Name** | Reject order |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants to stop an order the restaurant cannot fulfill. Customer—wants a definitive cancelled state. Weeklies—wants terminal transitions constrained by ownership and stage. |
| **Preconditions** | The owner is authenticated for the order's restaurant and the order is `Ordered`, `Accepted`, or `Preparing`. |
| **Trigger** | The owner chooses to reject or cancel the order. |
| **Main success scenario** | 1. The owner requests rejection.<br>2. Weeklies verifies the order and restaurant ownership.<br>3. Weeklies verifies that cancellation is still permitted.<br>4. Weeklies changes the status to `Cancelled`.<br>5. Weeklies updates restaurant analytics.<br>6. Weeklies confirms the cancellation. |
| **Extensions** | 2a. The order does not exist → Weeklies refuses the action.<br>2b. The order belongs to another restaurant → Weeklies refuses access.<br>3a. The order is `Ready`, `Delivered`, `Cancelled`, or another disallowed state → Weeklies rejects the transition.<br>5a. Analytics update fails → Weeklies keeps the cancelled status and continues. |
| **Postconditions** | The order status is `Cancelled` and no later fulfillment transition is valid. |

## UC24 — Start order preparation

| Part | Specification |
|---|---|
| **Name** | Start order preparation |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner and kitchen staff—want work-in-progress represented accurately. Customer—wants current status. Weeklies—wants sequential lifecycle transitions. |
| **Preconditions** | The owner is authenticated for the order's restaurant and the order status is `Accepted`. |
| **Trigger** | The owner indicates that preparation has begun. |
| **Main success scenario** | 1. The owner requests the preparation transition.<br>2. Weeklies verifies the order and restaurant ownership.<br>3. Weeklies verifies that the order was accepted.<br>4. Weeklies changes the status to `Preparing`.<br>5. Weeklies updates restaurant analytics.<br>6. Weeklies confirms the new state. |
| **Extensions** | 2a. The order is missing or belongs to another restaurant → Weeklies refuses the action.<br>3a. The order is not `Accepted` → Weeklies requires acceptance first.<br>5a. Analytics update fails → Weeklies keeps the preparing status and continues. |
| **Postconditions** | The order status is `Preparing` and it is eligible to be marked ready. |

## UC25 — Mark order ready

| Part | Specification |
|---|---|
| **Name** | Mark order ready |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants completed kitchen work reflected. Customer—wants to know the order can be collected or dispatched. Weeklies—wants sequential lifecycle transitions. |
| **Preconditions** | The owner is authenticated for the order's restaurant and the order status is `Preparing`. |
| **Trigger** | The owner indicates that preparation is complete. |
| **Main success scenario** | 1. The owner requests the ready transition.<br>2. Weeklies verifies the order and restaurant ownership.<br>3. Weeklies verifies that the order is being prepared.<br>4. Weeklies changes the status to `Ready`.<br>5. Weeklies updates restaurant analytics.<br>6. Weeklies confirms the new state. |
| **Extensions** | 2a. The order is missing or belongs to another restaurant → Weeklies refuses the action.<br>3a. The order is not `Preparing` → Weeklies rejects the transition.<br>5a. Analytics update fails → Weeklies keeps the ready status and continues. |
| **Postconditions** | The order status is `Ready` and it is eligible to be marked delivered. |

## UC26 — Mark order delivered

| Part | Specification |
|---|---|
| **Name** | Mark order delivered |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants fulfillment closed. Customer—wants final status and the ability to review. Weeklies—wants delivery recorded only after readiness. |
| **Preconditions** | The owner is authenticated for the order's restaurant and the order status is `Ready`. |
| **Trigger** | The owner indicates that the customer has received the order. |
| **Main success scenario** | 1. The owner requests the delivered transition.<br>2. Weeklies verifies the order and restaurant ownership.<br>3. Weeklies verifies that the order is ready.<br>4. Weeklies changes the status to `Delivered`.<br>5. Weeklies updates restaurant analytics.<br>6. Weeklies confirms completion. |
| **Extensions** | 2a. The order is missing or belongs to another restaurant → Weeklies refuses the action.<br>3a. The order is not `Ready` → Weeklies rejects the transition.<br>5a. Analytics update fails → Weeklies keeps the delivered status and continues. |
| **Postconditions** | The order status is `Delivered`, fulfillment is complete, and the owning customer may submit one review. |

## UC27 — Read customer reviews

| Part | Specification |
|---|---|
| **Name** | Read customer reviews |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants actionable feedback and aggregate reputation information. Review authors—want their submitted feedback represented accurately. Weeklies—wants review access scoped to the owner's restaurant. |
| **Preconditions** | The owner is authenticated for one restaurant. |
| **Trigger** | The owner opens the restaurant review module. |
| **Main success scenario** | 1. Weeklies identifies the session restaurant.<br>2. Weeklies calculates review count and average rating for that restaurant.<br>3. Weeklies retrieves one page of recent reviews and author information.<br>4. Weeklies shows the aggregate and individual reviews.<br>5. The owner navigates the review pages. |
| **Extensions** | 2a. No reviews exist → Weeklies shows a zero-review empty state.<br>3a. The owner chooses highest or lowest rating → Weeklies applies the requested rating order.<br>3b. The owner chooses a valid rating filter → Weeklies shows only matching reviews.<br>3c. The filter is invalid → Weeklies ignores it.<br>1a. Authentication is absent → Weeklies redirects to restaurant sign-in. |
| **Postconditions** | The owner has seen only reviews for the authenticated restaurant; no review is changed. |

## UC28 — Analyze restaurant performance

| Part | Specification |
|---|---|
| **Name** | Analyze restaurant performance |
| **Primary actor** | Signed-in restaurant owner |
| **Stakeholders & interests** | Owner—wants current revenue, volume, completion, status, item-popularity, and trend information. Weeklies—wants calculations based only on the session restaurant's orders. Customers—want their individual information not exposed in aggregates. |
| **Preconditions** | The owner is authenticated for one restaurant and the analytics schema is available. |
| **Trigger** | The owner opens restaurant analytics. |
| **Main success scenario** | 1. Weeklies retrieves the restaurant's orders.<br>2. Weeklies calculates total orders, revenue, average order value, completion rate, and popular items.<br>3. Weeklies records a current analytics snapshot.<br>4. Weeklies retrieves recent snapshot history and the current status distribution.<br>5. Weeklies shows summary metrics and trends.<br>6. The owner reviews restaurant performance. |
| **Extensions** | 1a. No orders exist → Weeklies records and shows zero-valued metrics.<br>2a. An order contains malformed details → Weeklies omits its malformed monetary/item details while retaining countable information.<br>2b. No item frequency can be determined → Weeklies shows no popular item.<br>3a. Snapshot recording fails → Weeklies reports or safely degrades without altering order fulfillment.<br>4a. Fewer than thirty snapshots exist → Weeklies shows the available history only.<br>1b. Authentication is absent → Weeklies redirects to restaurant sign-in. |
| **Postconditions** | The owner has seen analytics scoped to their restaurant, and a new snapshot records the calculated state when snapshot storage succeeds. |

## UC29 — Swap a single planned meal

| Part | Specification |
|---|---|
| **Name** | Swap a single planned meal |
| **Primary actor** | Signed-in customer |
| **Stakeholders & interests** | Customer—wants to replace one planned meal without regenerating or losing the rest of the plan. Restaurants—want only available, in-stock offerings substituted in. Weeklies—wants every planned item to respect the customer's declared allergies. |
| **Preconditions** | The customer is signed in and their plan has an item in the chosen date/meal slot. |
| **Trigger** | The customer chooses to swap one meal on the calendar. |
| **Main success scenario** | 1. The customer selects a planned date and meal period.<br>2. Weeklies lists the in-stock items from restaurants that are open at that meal time and free of the customer's stored allergies.<br>3. The customer picks a replacement item.<br>4. Weeklies re-checks the item's availability and allergens on the server.<br>5. Weeklies replaces only that date/meal slot and saves the plan.<br>6. Weeklies shows the calendar with the replacement and confirms the swap. |
| **Extensions** | 1a. The date or meal period is invalid → Weeklies rejects the request and leaves the plan unchanged.<br>1b. The slot has no planned meal → Weeklies reports that there is nothing to swap.<br>2a. No other item qualifies → Weeklies reports that no alternatives are available.<br>3a. The chosen item is already planned in that slot → Weeklies reports it and makes no change.<br>4a. The item does not exist → Weeklies rejects the swap.<br>4b. The item is out of stock → Weeklies rejects the swap.<br>4c. The restaurant is not open for business or is closed at that meal time → Weeklies rejects the swap.<br>4d. The item contains one of the customer's stored allergies → Weeklies rejects the swap, whatever allergies the request claims.<br>1c. Authentication is absent → Weeklies requires sign-in. |
| **Postconditions** | Exactly one slot holds the new item; every other date/meal entry in the plan is unchanged. On any rejection the stored plan is unchanged. |

> **Project 2 extension (single-meal swaps).** Added in Project 2. Availability and allergen checks run on the server against the account's stored allergies, never the request. Implemented in `proj2/meal_swap.py`, the `/menu/swap` and `/menu/swap/options` routes in `proj2/Flask_app.py`, and the calendar in `proj2/templates/index.html`; tested in `proj2/sef26tests/test_uc29_swap_meal.py`, `proj2/tests/integration/test_meal_swap_route.py`, and `proj2/tests/unit/test_meal_swap_*.py`.

## Coverage summary

The catalog contains 29 use cases:

- 18 customer/visitor goals
- 11 restaurant-owner goals
- Full coverage of implemented account, planning, browsing, ordering, receipt, review, fulfillment, and analytics flows
- Explicit extensions for authentication, ownership, invalid lifecycle transitions, malformed serialized data, meals with no eligible item, and best-effort analytics

Capabilities from the old `use_case.md` that remain future scope should receive separate use cases only when the project adopts the relevant actors and subsystems: geolocation/delivery zones, real checkout/payment, promotions, substitutions, driver dispatch/navigation, proof of delivery, refunds, and support disputes.
