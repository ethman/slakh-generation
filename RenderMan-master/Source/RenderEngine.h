/*
  ==============================================================================

    RenderEngine.h
    Created: 19 Feb 2017 9:47:15pm
    Author:  tollie

  ==============================================================================
*/

#ifndef RENDERENGINE_H_INCLUDED
#define RENDERENGINE_H_INCLUDED

#include <random>
#include <array>
#include <iomanip>
#include <sstream>
#include <string>
#include <typeinfo>
#include "Maximilian/maximilian.h"
#include "../JuceLibraryCode/JuceHeader.h"

using namespace juce;

typedef std::vector<std::pair<int, float>>  PluginPatch;

class RenderEngine
{
public:
    RenderEngine (int sr,
                  int bs) :
        sampleRate(sr),
        bufferSize(bs),
        plugin(nullptr)
    {
        maxiSettings::setup (sampleRate, 1, bufferSize);
    }

    virtual ~RenderEngine()
    {
        if (plugin != nullptr)
        {
            plugin->releaseResources();
            delete plugin;
        }
    }

    bool loadPreset (const std::string& path);

    bool loadPlugin (const std::string& path);
    
    int nMidiEvents () {
        return midiBuffer.getNumEvents();
    };

    bool loadMidi (const std::string& path);
    
    void setPatch (const PluginPatch patch);
    
    float getParameter (const int parameter);
    
    void setParameter (const int parameter, const float value);

    const PluginPatch getPatch();
    
    void renderMidi (const double renderLength);
    
    int hello () {
        DBG("hello");
        return 1;
    }

    void renderPatch (const uint8  midiNote,
                      const uint8  midiVelocity,
                      const double noteLength,
                      const double renderLength);

    const std::vector<double> getRMSFrames();

    const size_t getPluginParameterSize();

    const String getPluginParametersDescription();
    
    const String getPluginName();
    
    const String getPluginDescriptiveName();
    
    const String getProgramName();

    bool overridePluginParameter (const int   index,
                                  const float value);

    bool removeOverridenParameter (const int index);

    const std::vector<double> getAudioFrames();

    bool writeToWav(const std::string& path);
    
    void loadPluginState(const std::string& inputPath);
    
    void savePluginState(const std::string& outputPath);

private:
    void fillAudioFeatures (const AudioSampleBuffer& data);

    void ifTimeSetNoteOff (const double& noteLength,
                           const double& sampleRate,
                           const int&    bufferSize,
                           const uint8&  midiChannel,
                           const uint8&  midiPitch,
                           const uint8&  midiVelocity,
                           const int&    currentBufferIndex,
                           MidiBuffer&   bufferToNoteOff);

    void fillAvailablePluginParameters (PluginPatch& params);
    
    MidiFile             midiData;
    MidiBuffer           midiBuffer;
    
    double               sampleRate;
    int                  bufferSize;
    AudioPluginInstance* plugin;
    PluginDescription    pluginDescription;
    PluginPatch          pluginParameters;
    PluginPatch          overridenParameters;
    std::vector<double>  processedMonoAudioPreview;
    std::vector<double>  rmsFrames;
    double               currentRmsFrame;
};


#endif  // RENDERENGINE_H_INCLUDED
