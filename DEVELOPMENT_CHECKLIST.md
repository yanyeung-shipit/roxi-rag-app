# Development Checklist for ROXI

This checklist provides guidelines for developing new features or fixing issues in the ROXI system. Following these steps will help ensure you leverage existing solutions and avoid creating redundant components.

## Pre-Development Checklist

### 1. Understand the Current System

- [ ] Review the `PROCESSOR_REFERENCE.md` document
- [ ] Review the `processors/README.md` file
- [ ] Check if there are any relevant log files that might provide insights
- [ ] Run `python manage_processors.py` to see a list of existing components

### 2. Check for Existing Solutions

Before creating a new processing script:

- [ ] Check if an existing processor meets your needs
- [ ] Check if an existing solution can be adapted with minor modifications
- [ ] Look for similar names in the repository (use `find . -name "*keyword*"`)
- [ ] Consider whether the task should be handled by the existing adaptive processor

### 3. Error Handling

When encountering errors:

- [ ] Check logs for specific error details
- [ ] Search the codebase for similar error handling patterns
- [ ] Check if enhanced versions already exist for common issues:
  - SSL Connection Errors → Use `enhanced_batch_processor.py`
  - Database Connection Errors → Use `robust_process_to_50_percent.py`

### 4. Database Considerations

When working with databases:

- [ ] Use SQLAlchemy ORM instead of raw SQL when possible
- [ ] Implement proper error handling and reconnection logic
- [ ] Always include transaction rollback in error handlers
- [ ] Test with small batches before processing large amounts of data

### 5. System Resource Management

When creating resource-intensive processes:

- [ ] Implement proper sleep intervals between operations
- [ ] Include checkpointing capability to resume work
- [ ] Implement graceful shutdown and cleanup mechanisms
- [ ] Consider support for deep sleep mode when inactive

## Post-Development Checklist

After development:

- [ ] Update `PROCESSOR_REFERENCE.md` by running `python update_processor_docs.py`
- [ ] Add proper logging statements at appropriate levels (INFO, DEBUG, WARNING, ERROR)
- [ ] Consider whether any new redundant scripts should be moved to the `legacy` folder
- [ ] Update any relevant monitoring scripts to support your new component

## Monitoring Your Solution

- [ ] Ensure processing has proper progress tracking and reporting
- [ ] Use appropriate monitoring scripts (e.g. `enhanced_monitor_and_restart.sh`)
- [ ] Include deep sleep mode in long-running processes
- [ ] Implement resource usage tracking and optimization

## Best Practices

1. **Don't Reinvent the Wheel**: Use existing solutions where possible
2. **Document**: Always include docstrings and update documentation
3. **Error Handling**: Implement robust error handling and recovery
4. **Redundancy Control**: Move outdated scripts to the legacy folder
5. **Progress Tracking**: Always implement features to track and report progress

By following this checklist, you'll help maintain a clean, efficient, and understandable codebase for the ROXI system.