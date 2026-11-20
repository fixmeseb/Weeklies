"""
Which USDA FoodData Central foods each demo menu item is estimated from.

Restaurant dishes are not in USDA's data, so each item is matched to the closest food in
the Survey (FNDDS) dataset, or to a blend of foods for a plate with distinct parts (shrimp
and grits, chicken and waffle). Each part is given as (fdc_id, share of the item's
calories). proj2.nutrition.estimate_macros scales those foods so they add up to the
item's own calories, so the menu's calorie count stays as listed and USDA supplies the
mix of protein, carbs, fat and sodium. The results are estimates: expect them to be off
by 20-30% for any one dish.

The foods' nutrient values are in proj2/fndds_foods.py, generated from the USDA download
by scripts/build_fndds_snapshot.py, so seeding never needs the network.
"""

## Item name -> [(fdc_id, share of the item's calories), ...]; shares add up to 1
MATCHES = {
    # ---------------------------------------------------------- 1 Taste of Italy
    "Margherita Pizza": [(2708615, 1.0)],  # Pizza, cheese, restaurant, thin crust
    "Penne Arrabbiata": [(2708830, 1.0)],  # Pasta with tomato-based sauce, restaurant
    "Classic Tiramisu": [(2705702, 1.0)],  # Tiramisu
    "Caprese Salad": [(2705722, 0.6), (2709756, 0.4)],  # Mozzarella; tomato salad with oil
    "Pasta e Fagioli": [(2708927, 1.0)],  # Pasta with tomato sauce and beans
    # ----------------------------------------------------- 2 Green Garden Bistro
    "Avocado Quinoa Bowl": [
        (2708401, 0.4),  # Quinoa, fat added
        (2709223, 0.25),  # Avocado
        (2707359, 0.25),  # Black beans
        (2709918, 0.1),  # Corn, cooked with butter
    ],
    "Mediterranean Wrap": [(2709136, 0.7), (2707402, 0.3)],  # Vegetable wrap; hummus
    "Green Goddess Smoothie": [(2710152, 1.0)],  # Vegetable smoothie
    "Avocado Toast on Sourdough": [(2709223, 0.55), (2707601, 0.45)],  # Avocado; bakery toast
    "Lentil and Roasted Vegetable Bowl": [
        (2707424, 0.5),  # Lentils, fat added
        (2708414, 0.3),  # Brown rice (for farro)
        (2707402, 0.2),  # Hummus (for the tahini dressing)
    ],
    # --------------------------------------------------------- 3 Sunrise Griddle
    "Buttermilk Pancake Stack": [(2708304, 0.7), (2710273, 0.3)],  # Pancakes; pancake syrup
    "Veggie Scramble Bowl": [(2707208, 0.55), (2709472, 0.45)],  # Cheese scramble; home fries
    "Shrimp and Grits": [(2708369, 0.7), (2706363, 0.3)],  # Cheese grits; shrimp
    "Chicken and Waffle": [
        (2706052, 0.5),  # Fried chicken thigh, restaurant
        (2708325, 0.35),  # Waffle
        (2710273, 0.15),  # Syrup (for the hot honey)
    ],
    "Steel-Cut Oatmeal": [(2708380, 0.7), (2707599, 0.3)],  # Oatmeal; toast
    "Chorizo Breakfast Burrito": [(2707344, 1.0)],  # Egg burrito with sausage
    "Smashed Avo Toast": [(2709223, 0.55), (2707599, 0.45)],  # Avocado; toast
    "Biscuits and Sausage Gravy": [(2708744, 1.0)],  # Biscuit with gravy
    "Sweet Potato Breakfast Hash": [(2709697, 0.6), (2707359, 0.4)],  # Sweet potato; beans
    "Shakshuka": [(2707229, 1.0)],  # Eggs with tomatoes, fat added
    # ------------------------------------------------------ 4 Lotus Noodle House
    "Beef Pho": [(2707124, 1.0)],  # Pho with meat
    "Tofu Pad Thai": [(2708805, 1.0)],  # Pad Thai, meatless
    "Kung Pao Chicken": [(2706796, 0.7), (2708408, 0.3)],  # Kung pao chicken; rice
    "Vegetable Spring Rolls": [(2708700, 1.0)],  # Egg roll, meatless
    "Shrimp Summer Rolls": [
        (2708356, 0.5),  # Rice noodles
        (2706363, 0.3),  # Shrimp
        (2707546, 0.2),  # Peanut sauce
    ],
    "Mapo Tofu": [(2707477, 0.6), (2708408, 0.4)],  # Tofu and vegetables, soy sauce; rice
    "Thai Green Curry with Chicken": [(2706438, 1.0)],  # Chicken curry with rice
    "Thai Iced Tea": [(2705402, 1.0)],  # Sweetened condensed milk (the tea has no calories)
    # ----------------------------------------------------- 5 Casa Verde Taqueria
    "Carnitas Tacos": [(2708517, 1.0)],  # Taco, corn tortilla, pork, cheese
    "Grilled Fish Tacos": [(2708529, 1.0)],  # Taco, fish
    "Black Bean and Sweet Potato Burrito": [(2708547, 0.7), (2709697, 0.3)],
    "Chicken Tinga Bowl": [(2708563, 1.0)],  # Burrito bowl, chicken, beans and rice
    "Elote Cup": [(2709918, 1.0)],  # Corn, cooked with butter
    "Chips and Guacamole": [(2708202, 0.55), (2709307, 0.45)],  # Tortilla chips; guacamole
    "Churros with Chocolate": [(2708070, 0.75), (2705472, 0.25)],  # Churros; hot chocolate
    "Horchata": [(2710602, 1.0)],  # Horchata, made with water
    # -------------------------------------------------------- 6 Saffron Tandoor
    "Chicken Tikka Masala": [(2706438, 1.0)],  # Chicken curry with rice
    "Chana Masala": [(2707415, 0.6), (2708408, 0.4)],  # Chickpeas, fat added; rice
    "Chana Masala with Basmati Rice": [(2707415, 0.6), (2708408, 0.4)],
    "Palak Paneer": [(2709631, 0.65), (2708408, 0.35)],  # Palak paneer; rice
    "Lamb Rogan Josh": [(2706660, 1.0)],  # Lamb stew
    "Vegetable Samosas": [(2708730, 0.85), (2709269, 0.15)],  # Samosa; tamarind
    "Garlic Naan": [(2707613, 1.0)],  # Naan
    "Tandoori Fish Tikka": [(2706241, 1.0)],  # Cod, baked or broiled
    "Mango Lassi": [(2705426, 0.7), (2709242, 0.3)],  # Whole-milk fruit yogurt; mango
    "Gulab Jamun": [(2708062, 0.6), (2710278, 0.4)],  # Doughnut; simple syrup
    # ---------------------------------------------------------- 7 Olive & Ember
    "Chicken Shawarma Plate": [(2706537, 0.65), (2707616, 0.35)],  # Chicken and rice; pita
    "Falafel Wrap": [(2707483, 1.0)],  # Falafel sandwich
    "Greek Salad with Feta": [(2709830, 0.6), (2705714, 0.4)],  # Greek salad; feta
    "Lamb Kofta Kebabs": [(2705907, 0.65), (2708408, 0.35)],  # Ground lamb; rice
    "Hummus and Warm Pita": [(2707402, 0.55), (2707616, 0.45)],  # Hummus; pita
    "Spanakopita": [(2708729, 1.0)],
    "Grilled Salmon Quinoa Bowl": [(2706286, 0.55), (2708401, 0.45)],  # Salmon; quinoa
    "Pistachio Baklava": [(2708044, 1.0)],
    # -------------------------------------------------------- 8 Tokyo Bento Bar
    "Salmon Avocado Roll": [(2708963, 1.0)],  # Sushi roll, salmon
    "Chicken Katsu Curry": [
        (2705978, 0.5),  # Fried coated chicken breast, restaurant
        (2708408, 0.35),  # Rice
        (2706437, 0.15),  # Chicken curry (the sauce)
    ],
    "Tonkotsu Ramen": [(2709153, 1.0)],  # Ramen bowl
    "Tofu Bibimbap": [(2708950, 1.0)],  # Bibimbap
    "Korean Fried Chicken Wings": [(2706068, 1.0)],  # Fried coated wings, restaurant
    "Edamame with Sea Salt": [(2707436, 1.0)],
    "Miso Soup": [(2707455, 1.0)],  # Soup, miso or tofu
    "Matcha Mochi Ice Cream": [(2705629, 1.0)],  # Ice cream
    "Teriyaki Salmon Bento": [
        (2706286, 0.45),  # Salmon, baked
        (2708408, 0.4),  # Rice
        (2707436, 0.15),  # Edamame
    ],
    # ------------------------------------------------------ 9 Bayou Smokehouse
    "Pulled Pork Sandwich": [(2706975, 1.0)],  # Barbecue pork sandwich, white bun
    "Smoked Brisket Plate": [(2705851, 1.0)],  # Beef brisket
    "Jerk Chicken with Rice and Peas": [
        (2706054, 0.55),
        (2708990, 0.45),
    ],  # Chicken; beans and rice
    "Blackened Catfish": [(2706236, 1.0)],  # Catfish, grilled
    "Baked Mac and Cheese": [(2708811, 1.0)],
    "Smoky Collard Greens": [(2709582, 1.0)],  # Collards cooked with oil
    "Fried Sweet Plantains": [(2709559, 1.0)],  # Plantain cooked with oil
    "Banana Pudding": [(2705697, 1.0)],
    "Bourbon Pecan Pie": [(2708015, 1.0)],
    # ------------------------------------------------------ 10 Daily Grind Cafe
    "Ham and Gruyere Croissant": [(2707678, 0.45), (2706969, 0.55)],  # Croissant; ham and cheese
    "Greek Yogurt Parfait": [(2705450, 1.0)],
    "Cold Brew Coffee": [(2710375, 1.0)],  # Coffee, brewed
    "Turkey Pesto Panini": [(2706986, 1.0)],  # Turkey sandwich with cheese, restaurant
    "Tomato Basil Soup": [(2709757, 1.0)],
    "Dark Chocolate Brownie": [(2707904, 1.0)],
    "Mango Chia Pudding": [
        (2707590, 0.35),  # Chia seeds
        (2705404, 0.4),  # Soy milk, sweetened
        (2709242, 0.25),  # Mango
    ],
    "Bagel with Lox and Cream Cheese": [
        (2707684, 0.45),  # Bagel
        (2705760, 0.3),  # Cream cheese
        (2706292, 0.25),  # Salmon, smoked
    ],
    # ------------------------------------------------ 11 Valley Farmhouse Kitchen
    "Lucky Lunch": [(2709136, 0.75), (2706336, 0.25)],  # Vegetable wrap; shellfish (sea cucumber)
    "Roots Platter": [(2709663, 0.5), (2709955, 0.5)],  # Carrots; parsnips
    "Magic Rock Candy": [(2710360, 1.0)],  # Candy, hard
}
