#!/usr/bin/env python3
"""
Interactive Command-Line Todo List Application in Python.
Allows users to add, view, complete, and delete tasks.
"""

def show_menu():
    print("\n" + "="*30)
    print("       TODO LIST APP")
    print("="*30)
    print("1. View Tasks")
    print("2. Add a Task")
    print("3. Mark Task as Complete")
    print("4. Delete a Task")
    print("5. Exit")
    print("="*30)

def main():
    tasks = []
    
    while True:
        show_menu()
        choice = input("Choose an option (1-5): ").strip()
        
        if choice == '1':
            print("\n--- YOUR TASKS ---")
            if not tasks:
                print("Your todo list is empty! Add some tasks.")
            else:
                for index, task in enumerate(tasks, start=1):
                    status = "[✓]" if task["completed"] else "[ ]"
                    print(f"{index}. {status} {task['title']}")
                    
        elif choice == '2':
            title = input("\nEnter the task description: ").strip()
            if title:
                tasks.append({"title": title, "completed": False})
                print(f"Task '{title}' added successfully!")
            else:
                print("Task description cannot be empty.")
                
        elif choice == '3':
            if not tasks:
                print("\nNo tasks to complete.")
                continue
                
            print("\n--- CURRENT TASKS ---")
            for index, task in enumerate(tasks, start=1):
                status = "[✓]" if task["completed"] else "[ ]"
                print(f"{index}. {status} {task['title']}")
                
            try:
                task_num = int(input("\nEnter the number of the task to mark complete: "))
                if 1 <= task_num <= len(tasks):
                    tasks[task_num - 1]["completed"] = True
                    print(f"Task '{tasks[task_num - 1]['title']}' marked as complete!")
                else:
                    print("Invalid task number.")
            except ValueError:
                print("Please enter a valid number.")
                
        elif choice == '4':
            if not tasks:
                print("\nNo tasks to delete.")
                continue
                
            print("\n--- CURRENT TASKS ---")
            for index, task in enumerate(tasks, start=1):
                status = "[✓]" if task["completed"] else "[ ]"
                print(f"{index}. {status} {task['title']}")
                
            try:
                task_num = int(input("\nEnter the number of the task to delete: "))
                if 1 <= task_num <= len(tasks):
                    removed = tasks.pop(task_num - 1)
                    print(f"Task '{removed['title']}' deleted successfully!")
                else:
                    print("Invalid task number.")
            except ValueError:
                print("Please enter a valid number.")
                
        elif choice == '5':
            print("\nThank you for using Todo List App. Goodbye!")
            break
        else:
            print("Invalid option. Please choose a number between 1 and 5.")

if __name__ == "__main__":
    main()
