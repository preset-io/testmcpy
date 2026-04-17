import React, { useState, useCallback } from 'react'
import { ChevronLeft, ChevronRight, Check, Circle, SkipForward } from 'lucide-react'

/**
 * Reusable multi-step wizard component.
 *
 * Props:
 *   steps: Array of { label, component: React element/function, validate?: () => bool|string, optional?: bool }
 *   onComplete: (data) => void - called when wizard finishes
 *   onCancel: () => void - called when wizard is cancelled
 *   title: string - wizard title
 *   data: object - shared wizard data passed to each step
 *   setData: (data) => void - update shared wizard data
 */
function Wizard({ steps, onComplete, onCancel, title, data, setData }) {
  const [currentStep, setCurrentStep] = useState(0)
  const [validationError, setValidationError] = useState(null)
  const [direction, setDirection] = useState('forward') // 'forward' or 'backward'
  const [animating, setAnimating] = useState(false)

  const isLastStep = currentStep === steps.length - 1
  const isFirstStep = currentStep === 0
  const step = steps[currentStep]

  const animateTransition = useCallback((newStep, dir) => {
    setDirection(dir)
    setAnimating(true)
    // Short delay for exit animation, then switch step
    setTimeout(() => {
      setCurrentStep(newStep)
      setAnimating(false)
    }, 150)
  }, [])

  const handleNext = useCallback(() => {
    setValidationError(null)

    // Run validation if step has a validate function
    if (step.validate) {
      const result = step.validate(data)
      if (result !== true && result !== null && result !== undefined) {
        // result is either false or an error string
        setValidationError(typeof result === 'string' ? result : 'Please complete this step before continuing.')
        return
      }
    }

    if (isLastStep) {
      onComplete(data)
    } else {
      animateTransition(currentStep + 1, 'forward')
    }
  }, [step, data, isLastStep, currentStep, onComplete, animateTransition])

  const handleBack = useCallback(() => {
    setValidationError(null)
    if (!isFirstStep) {
      animateTransition(currentStep - 1, 'backward')
    }
  }, [isFirstStep, currentStep, animateTransition])

  const handleSkip = useCallback(() => {
    setValidationError(null)
    if (step.optional && !isLastStep) {
      animateTransition(currentStep + 1, 'forward')
    }
  }, [step, isLastStep, currentStep, animateTransition])

  const handleStepClick = useCallback((idx) => {
    // Allow clicking on previous steps or current step
    if (idx < currentStep) {
      setValidationError(null)
      animateTransition(idx, 'backward')
    }
  }, [currentStep, animateTransition])

  // Determine step completion status
  const getStepStatus = (idx) => {
    if (idx < currentStep) return 'completed'
    if (idx === currentStep) return 'current'
    return 'upcoming'
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-0 md:p-4">
      <div className="bg-surface-elevated border border-border rounded-none md:rounded-xl w-full h-full md:h-auto md:max-w-3xl md:max-h-[85vh] flex flex-col shadow-xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex-shrink-0">
          <h2 className="text-lg font-bold text-text-primary">{title}</h2>

          {/* Progress indicator */}
          <div className="flex items-center gap-1 mt-3 overflow-x-auto pb-1">
            {steps.map((s, idx) => {
              const status = getStepStatus(idx)
              return (
                <React.Fragment key={idx}>
                  {idx > 0 && (
                    <div className={`flex-shrink-0 w-8 h-0.5 transition-colors duration-300 ${
                      status === 'completed' || status === 'current' ? 'bg-primary' : 'bg-border'
                    }`} />
                  )}
                  <button
                    onClick={() => handleStepClick(idx)}
                    disabled={idx > currentStep}
                    className={`flex items-center gap-1.5 flex-shrink-0 px-2 py-1 rounded-md transition-all duration-200 ${
                      status === 'current'
                        ? 'bg-primary/10 text-primary'
                        : status === 'completed'
                          ? 'text-success hover:bg-surface-hover cursor-pointer'
                          : 'text-text-disabled cursor-default'
                    }`}
                  >
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-300 ${
                      status === 'completed'
                        ? 'bg-success text-white'
                        : status === 'current'
                          ? 'bg-primary text-white'
                          : 'bg-border text-text-disabled'
                    }`}>
                      {status === 'completed' ? (
                        <Check size={10} strokeWidth={3} />
                      ) : (
                        idx + 1
                      )}
                    </div>
                    <span className={`text-xs font-medium hidden sm:inline ${
                      status === 'current' ? 'text-primary' :
                      status === 'completed' ? 'text-text-secondary' : 'text-text-disabled'
                    }`}>
                      {s.label}
                    </span>
                    {s.optional && status !== 'completed' && (
                      <span className="text-[9px] text-text-tertiary">(optional)</span>
                    )}
                  </button>
                </React.Fragment>
              )
            })}
          </div>
        </div>

        {/* Step Content */}
        <div className="flex-1 overflow-auto p-6 min-h-0">
          <div className={`transition-all duration-150 ${
            animating
              ? direction === 'forward'
                ? 'opacity-0 translate-x-4'
                : 'opacity-0 -translate-x-4'
              : 'opacity-100 translate-x-0'
          }`}>
            {/* Step label */}
            <div className="mb-4">
              <h3 className="text-base font-semibold text-text-primary">
                Step {currentStep + 1}: {step.label}
              </h3>
            </div>

            {/* Render step component */}
            {typeof step.component === 'function'
              ? step.component({ data, setData, validationError })
              : step.component
            }

            {/* Validation error */}
            {validationError && (
              <div className="mt-3 p-3 bg-error/10 border border-error/30 rounded-lg text-sm text-error">
                {validationError}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border flex items-center justify-between flex-shrink-0">
          <div>
            {onCancel && (
              <button
                onClick={onCancel}
                className="btn btn-ghost text-sm"
              >
                Cancel
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!isFirstStep && (
              <button
                onClick={handleBack}
                className="btn btn-secondary text-sm"
              >
                <ChevronLeft size={14} />
                Back
              </button>
            )}
            {step.optional && !isLastStep && (
              <button
                onClick={handleSkip}
                className="btn btn-ghost text-sm"
              >
                <SkipForward size={14} />
                Skip
              </button>
            )}
            <button
              onClick={handleNext}
              className="btn btn-primary text-sm"
            >
              {isLastStep ? (
                <>
                  <Check size={14} />
                  Finish
                </>
              ) : (
                <>
                  Next
                  <ChevronRight size={14} />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Wizard
