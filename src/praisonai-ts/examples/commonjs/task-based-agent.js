const { Agent, Task } = require('praisonai');

// Create a task-based agent
const agent = new Agent({
  name: "TaskMaster",
  role: "Assistant",
  goal: "Complete tasks efficiently",
  backstory: "You are an AI assistant that helps complete tasks step by step."
});

// Create a task with dependencies
const mainTask = new Task({
  name: "Write Blog Post",
  description: "Write a blog post about artificial intelligence",
  expected_output: "A complete blog post",
  dependencies: []
});

// Execute the task
agent.execute(mainTask)
  .then(response => {
    console.log('\nBlog Post:');
    console.log(response);
  })
  .catch(error => console.error('Error:', error));
