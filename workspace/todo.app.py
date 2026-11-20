#!/usr/bin/env python3
"""
Enhanced Interactive Command-Line Todo List Application in Python.
Features:
- Add tasks with priority (High, Medium, Low) and due dates.
- View tasks sorted or filtered by status (All, Pending, Completed) and priority.
- Mark tasks as complete or incomplete (toggle).
- Edit existing task descriptions and priorities.
- Delete individual tasks or clear all completed tasks.
- Persistent storage using JSON so your tasks are saved between runs.
- Search functionality.
"""

import json
import os

FILENAME = "tasks.json"

def load_tasks():
    if os.path.exists(FILENAME):
        try:
            with open(FILENAME, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_tasks(tasks):
    with open(FILENAME, "w") as f:
        json.dump(tasks, f, indent=4)

def show_menu():
    print("\n" + "="*50)
    print("           ENHANCED TODO LIST APP")
    print("="*50)
    print("1. View Tasks (Filter / Sort)")
    print("2. Add a Task")
    print("3. Toggle Task Complete / Incomplete")
    print("4. Edit a Task")
    print("5. Delete a Task")
    print("6. Clear Completed Tasks")
    print("7. Search Tasks")
    print("8. Exit")
    print("="*50)

def display_task_list(tasks_to_show):
    if not tasks_to_show:
        print("\nNo tasks found.")
        return
    
    print("\n" + "-"*75)
    print(f"{'No.':<4} | {'Status':<10} | {'Priority':<10} | {'Due Date':<12} | {'Description'}")
    print("-"*75)
    
    for index, task in enumerate(tasks_to_show, start=1):
        status = "Done [✓]" if task.get("completed", False) else "Pending [ ]"
        priority = task.get("priority", "Medium")
        due_date = task.get("due_date", "None")
        title = task.get("title", "")
        print(f"{index:<4} | {status:<10} | {priority:<10} | {due_date:<12} | {title}")
    print("-"*75)

def main():
    tasks = load_tasks()
    
    while True:
        show_menu()
        choice = input("Choose an option (1-8): ").strip()
        
        if choice == '1':
            if not tasks:
                print("\nYour todo list is empty! Add some tasks.")
                continue
            
            print("\n--- VIEW OPTIONS ---")
            print("1. View All Tasks")
            print("2. View Pending Tasks Only")
            print("3. View Completed Tasks Only")
            print("4. Sort by Priority (High -> Low)")
            view_choice = input("Select view option (1-4): ").strip()
            
            if view_choice == '1':
                display_task_list(tasks)
            elif view_choice == '2':
                pending = [t for t in tasks if not t.get("completed", False)]
                display_task_list(pending)
            elif view_choice == '3':
                completed = [t for t in tasks if t.get("completed", False)]
                display_task_list(completed)
            elif view_choice == '4':
                priority_order = {"High": 1, "Medium": 2, "Low": 3}
                sorted_tasks = sorted(tasks, key=lambda x: priority_order.get(x.get("priority", "Medium"), 2))
                display_task_list(sorted_tasks)
            else:
                print("Invalid view option, showing all tasks.")
                display_task_list(tasks)
                
        elif choice == '2':
            title = input("\nEnter the task description: ").strip()
            if not title:
                print("Task description cannot be empty.")
                continue
                
            print("Select Priority:")
            print("1. High")
            print("2. Medium (Default)")
            print("3. Low")
            p_choice = input("Choose priority (1-3): ").strip()
            if p_choice == '1':
                priority = "High"
            elif p_choice == '3':
                priority = "Low"
            else:
                priority = "Medium"
                
            due_date = input("Enter due date (e.g., YYYY-MM-DD or 'Tomorrow', optional): ").strip()
            if not due_date:
                due_date = "None"
                
            new_task = {
                "title": title,
                "completed": False,
                "priority": priority,
                "due_date": due_date
            }
            tasks.append(new_task)
            save_tasks(tasks)
            print(f"Task '{title}' added successfully!")
            
        elif choice == '3':
            if not tasks:
                print("\nNo tasks available.")
                continue
                
            display_task_list(tasks)
            try:
                task_num = int(input("\nEnter the task number to toggle completion status: "))
                if 1 <= task_num <= len(tasks):
                    task = tasks[task_num - 1]
                    task["completed"] = not task["completed"]
                    save_tasks(tasks)
                    status_str = "Complete [✓]" if task["completed"] else "Pending [ ]"
                    print(f"Task '{task['title']}' status updated to: {status_str}")
                else:
                    print("Invalid task number.")
            except ValueError:
                print("Please enter a valid number.")
                
        elif choice == '4':
            if not tasks:
                print("\nNo tasks to edit.")
                continue
                
            display_task_list(tasks)
            try:
                task_num = int(input("\nEnter the task number to edit: "))
                if 1 <= task_num <= len(tasks):
                    task = tasks[task_num - 1]
                    print(f"\nEditing Task: {task['title']}")
                    new_title = input(f"New description (leave blank to keep '{task['title']}'): ").strip()
                    if new_title:
                        task["title"] = new_title
                        
                    print(f"Current priority: {task.get('priority', 'Medium')}")
                    print("1. High | 2. Medium | 3. Low | Press Enter to keep current")
                    p_choice = input("Choose new priority: ").strip()
                    if p_choice == '1':
                        task["priority"] = "High"
                    elif p_choice == '2':
                        task["priority"] = "Medium"
                    elif p_choice == '3':
                        task["priority"] = "Low"
                        
                    new_due = input(f"New due date (leave blank to keep '{task.get('due_date', 'None')}'): ").strip()
                    if new_due:
                        task["due_date"] = new_due
                        
                    save_tasks(tasks)
                    print("Task updated successfully!")
                else:
                    print("Invalid task number.")
            except ValueError:
                print("Please enter a valid number.")
                
        elif choice == '5':
            if not tasks:
                print("\nNo tasks to delete.")
                continue
                
            display_task_list(tasks)
            try:
                task_num = int(input("\nEnter the task number to delete: "))
                if 1 <= task_num <= len(tasks):
                    removed = tasks.pop(task_num - 1)
                    save_tasks(tasks)
                    print(f"Task '{removed['title']}' deleted successfully!")
                else:
                    print("Invalid task number.")
            except ValueError:
                print("Please enter a valid number.")
                
        elif choice == '6':
            completed_tasks = [t for t in tasks if t.get("completed", False)]
            if not completed_tasks:
                print("\nNo completed tasks to clear.")
            else:
                confirm = input(f"\nAre you sure you want to delete {len(completed_tasks)} completed task(s)? (y/n): ").strip().lower()
                if confirm == 'y':
                    tasks = [t for t in tasks if not t.get("completed", False)]
                    save_tasks(tasks)
                    print("All completed tasks cleared successfully!")
                else:
                    print("Operation cancelled.")
                    
        elif choice == '7':
            if not tasks:
                print("\nNo tasks to search.")
                continue
            query = input("\nEnter keyword to search in task descriptions: ").strip().lower()
            if query:
                results = [t for t in tasks if query in t.get("title", "").lower()]
                print(f"\n--- SEARCH RESULTS FOR '{query}' ---")
                display_task_list(results)
            else:
                print("Search query cannot be empty.")
                
        elif choice == '8':
            print("\nThank you for using Enhanced Todo List App. Goodbye!")
            break
        else:
            print("Invalid option. Please choose a number between 1 and 8.")

if __name__ == "__main__":
    main()
