# Python Basics: A Short Tutorial

Python is a versatile, high-level programming language that is easy to learn and widely used for various applications, from web development to data analysis. This tutorial will cover essential Python concepts to get you started.

## 1. **Installing Python**

To install Python, download it from the official [Python website](https://www.python.org/downloads/) and follow the installation instructions for your operating system. Ensure you check the box to add Python to your system PATH.

## 2. **Running Python Code**

You can run Python code in several ways:
- **Interactive Shell:** Open your terminal and type `python` or `python3`.
- **Script File:** Create a `.py` file (e.g., `script.py`) and run it using `python script.py`.

## 3. **Basic Syntax**

### Hello World
A simple program to print "Hello, World!" looks like this:

```python
print("Hello, World!")
```

### Variables and Data Types
Python supports various data types like integers, floats, strings, and booleans.

```python
# This is a comment
name = "Alice"         # String
age = 30               # Integer
weight = 65.5          # Float
is_student = True      # Boolean
```

### Lists
Lists hold ordered collections of items.

```python
fruits = ["apple", "banana", "cherry"]
print(fruits[0])  # Output: apple
```

### Tuples
Tuples are similar to lists but are immutable.

```python
coordinates = (10.0, 20.0)
print(coordinates[1])  # Output: 20.0
```

### Dictionaries
Dictionaries store key-value pairs.

```python
person = {"name": "Alice", "age": 30}
print(person["name"])  # Output: Alice
```

## 4. **Control Flow**

### Conditional Statements
Use `if`, `elif`, and `else` for decision-making.

```python
if age < 18:
    print("Minor")
elif age >= 18 and age < 65:
    print("Adult")
else:
    print("Senior")
```

### Loops
Python has `for` and `while` loops for iteration.

**For Loop:**

```python
for fruit in fruits:
    print(fruit)
```

**While Loop:**

```python
count = 0
while count < 5:
    print(count)
    count += 1
```

## 5. **Functions**

Functions are defined using the `def` keyword.

```python
def greet(name):
    return f"Hello, {name}!"

print(greet("Alice"))  # Output: Hello, Alice!
```

## 6. **Modules and Libraries**

You can import libraries to extend Python's functionality. For example, to use the `math` module:

```python
import math
print(math.sqrt(16))  # Output: 4.0
```

## 7. **Conclusion**

This quick tutorial introduced you to the basics of Python, including installation, syntax, data types, control flow, functions, and modules. Python offers a rich ecosystem, and there's much more to explore. Happy coding!