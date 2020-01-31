/*
  ==============================================================================

    RenderEngine.cpp
    Created: 19 Feb 2017 9:47:15pm
    Author:  tollie

  ==============================================================================
*/

#include "RenderEngine.h"
//==============================================================================
bool RenderEngine::loadPreset (const std::string& path)
{
    MemoryBlock mb;
    File file = File(path);
    file.loadFileAsData(mb);
//    bool loaded = VST3PluginFormat::loadFromFXBFile (plugin, mb.getData(), mb.getSize());
//    bool loaded = VST3PluginFormat::setStateFromVSTPresetFile(plugin, mb);
    return false;
}

//==============================================================================
bool RenderEngine::loadPlugin (const std::string& path)
{
    OwnedArray<PluginDescription> pluginDescriptions;
    KnownPluginList pluginList;
    AudioPluginFormatManager pluginFormatManager;

    pluginFormatManager.addDefaultFormats();

    for (int i = pluginFormatManager.getNumFormats(); --i >= 0;)
    {
        pluginList.scanAndAddFile (String (path),
                                   true,
                                   pluginDescriptions,
                                   *pluginFormatManager.getFormat(i));
    }

    // If there is a problem here first check the preprocessor definitions
    // in the projucer are sensible - is it set up to scan for plugin's?
    jassert (pluginDescriptions.size() > 0);

    String errorMessage;

    if (plugin != nullptr) delete plugin;
    plugin = pluginFormatManager.createPluginInstance (*pluginDescriptions[0],
                                                       sampleRate,
                                                       bufferSize,
                                                       errorMessage);
    if (plugin != nullptr)
    {
        // Success so set up plugin, then set up features and get all available
        // parameters from this given plugin.
        plugin->prepareToPlay (sampleRate, bufferSize);
        plugin->setNonRealtime (true);

        // Resize the pluginParameters patch type to fit this plugin and init
        // all the values to 0.0f!
        fillAvailablePluginParameters (pluginParameters);
        
        pluginDescription = plugin->getPluginDescription();

        return true;
    }

    std::cout << "RenderEngine::loadPlugin error: "
    << errorMessage.toStdString()
    << std::endl;

    return false;
}

bool RenderEngine::loadMidi(const std::string& path)
{
    File file = File(path);
    FileInputStream fileStream(file);
    MidiFile midiFile;
    midiFile.readFrom(fileStream);
    midiFile.convertTimestampTicksToSeconds();
    midiBuffer.clear();
    
    for (int t = 0; t < midiFile.getNumTracks(); t++) {
        const MidiMessageSequence* track = midiFile.getTrack(t);
        for (int i = 0; i < track->getNumEvents(); i++) {
            MidiMessage& m = track->getEventPointer(i)->message;
            int sampleOffset = (int)(sampleRate * m.getTimeStamp());
            midiBuffer.addEvent(m, sampleOffset);
        }
    }
    
    return midiBuffer.getNumEvents();
}

void RenderEngine::renderMidi (const double renderLength)
{
    // Data structure to hold multi-channel audio data.
    AudioSampleBuffer audioBuffer (plugin->getTotalNumOutputChannels(),
                                   bufferSize);
    
    int numberOfBuffers = int (std::ceil (renderLength * sampleRate / bufferSize));
    
    // Clear and reserve memory for the audio storage!
    processedMonoAudioPreview.clear();
    processedMonoAudioPreview.reserve (numberOfBuffers * bufferSize);
    
    plugin->prepareToPlay (sampleRate, bufferSize);
    
    MidiBuffer renderMidiBuffer;
    MidiBuffer::Iterator it(midiBuffer);
    
    MidiMessage m;
    int sampleNumber = -1;
    bool isMessageBetween;
    bool bufferRemaining = it.getNextEvent(m, sampleNumber);
    
    for (int i = 0; i < numberOfBuffers; ++i)
    {
        double start = i * bufferSize;
        double end = (i + 1) * bufferSize;
        
        isMessageBetween = sampleNumber >= start && sampleNumber < end;
        do {
            if (isMessageBetween) {
                renderMidiBuffer.addEvent(m, sampleNumber - start);
                bufferRemaining = it.getNextEvent(m, sampleNumber);
                isMessageBetween = sampleNumber >= start && sampleNumber < end;
            }
        } while (isMessageBetween && bufferRemaining);
        
        // Turn Midi to audio via the vst.
        plugin->processBlock (audioBuffer, renderMidiBuffer);
        
        // Get audio features and fill the datastructure.
        fillAudioFeatures (audioBuffer);
    }
}

//==============================================================================
void RenderEngine::renderPatch (const uint8  midiNote,
                                const uint8  midiVelocity,
                                const double noteLength,
                                const double renderLength)
{
    // Get the note on midiBuffer.
    MidiMessage onMessage = MidiMessage::noteOn (1,
                                                 midiNote,
                                                 midiVelocity);
    
    MidiMessage offMessage = MidiMessage::noteOff (1,
                                                 midiNote,
                                                 midiVelocity);
    
    onMessage.setTimeStamp(0);
    offMessage.setTimeStamp(noteLength * sampleRate);
    midiBuffer.addEvent (onMessage, onMessage.getTimeStamp());
    midiBuffer.addEvent (offMessage, offMessage.getTimeStamp());
    renderMidi(renderLength);
}

//=============================================================================
void RenderEngine::fillAudioFeatures (const AudioSampleBuffer& data)
{
    // Keep it auto as it may or may not be double precision.
    const auto readptrs = data.getArrayOfReadPointers();
    for (int i = 0; i < data.getNumSamples(); ++i)
    {
        // Mono the frame.
        int channel = 0;
        auto currentFrame = readptrs[channel][i];
        const int numberChannels = data.getNumChannels();

        while (++channel < numberChannels)
            currentFrame += readptrs[channel][i];

        currentFrame /= numberChannels;

        // Save the audio for playback and plotting!
        processedMonoAudioPreview.push_back (currentFrame);
    }
}

//=============================================================================
void RenderEngine::ifTimeSetNoteOff (const double& noteLength,
                                     const double& sampleRate,
                                     const int&    bufferSize,
                                     const uint8&  midiChannel,
                                     const uint8&  midiPitch,
                                     const uint8&  midiVelocity,
                                     const int&    currentBufferIndex,
                                     MidiBuffer&   bufferToNoteOff)
{
    double eventFrame = noteLength * sampleRate;
    bool bufferBeginIsBeforeEvent = currentBufferIndex * bufferSize < eventFrame;
    bool bufferEndIsAfterEvent = (currentBufferIndex + 1) * bufferSize >= eventFrame;
    bool noteOffEvent = bufferBeginIsBeforeEvent && bufferEndIsAfterEvent;
    if (noteOffEvent)
    {
        MidiBuffer midiOffBuffer;
        MidiMessage offMessage = MidiMessage::noteOff (midiChannel,
                                                       midiPitch,
                                                       midiVelocity);
        offMessage.setTimeStamp(eventFrame);
        midiOffBuffer.addEvent(offMessage, offMessage.getTimeStamp());
        bufferToNoteOff = midiOffBuffer;
    }
}

//==============================================================================
bool RenderEngine::overridePluginParameter (const int   index,
                                            const float value)
{
    int biggestParameterIndex = pluginParameters.size() - 1;

    if (biggestParameterIndex < 0)
    {
        std::cout << "RenderEngine::overridePluginParameter error: " <<
                     "No patch set. Is the plugin loaded?" << std::endl;
        return false;
    }
    else if (index > pluginParameters[biggestParameterIndex].first)
    {
        std::cout << "RenderEngine::overridePluginParameter error: " <<
                     "Overriden parameter index is greater than the biggest parameter index." <<
                     std::endl;
        return false;
    }
    else if (index < 0)
    {
        std::cout << "RenderEngine::overridePluginParameter error: " <<
                     "Overriden parameter index is less than the smallest parameter index." <<
                     std::endl;
        return false;
    }
    else if (value < 0.0 || value > 1.0)
    {
        std::cout << "RenderEngine::overridePluginParameter error: " <<
                     "Keep the overriden value between 0.0 and 1.0." <<
                     std::endl;
        return false;
    }

    auto iterator = std::find_if (overridenParameters.begin(),
                                  overridenParameters.end(),
                                  [&index] (const std::pair<int, float>& parameter)
                                  {
                                      return parameter.first == index;
                                  });

    bool exists = (iterator != overridenParameters.end());

    if (exists)
        iterator->second = value;
    else
        overridenParameters.push_back(std::make_pair(index, value));

    return true;
}

//==============================================================================
bool RenderEngine::removeOverridenParameter (const int index)
{
    int biggestParameterIndex = pluginParameters.size() - 1;

    if (biggestParameterIndex < 0)
    {
        std::cout << "RenderEngine::removeOverridenParameter error: " <<
                     "No patch set. Is the plugin loaded?" << std::endl;
        return false;
    }
    else if (index > pluginParameters[biggestParameterIndex].first)
    {
        std::cout << "RenderEngine::removeOverridenParameter error: " <<
                     "Overriden parameter index is greater than the biggest parameter index." <<
                     std::endl;
        return false;
    }
    else if (index < 0)
    {
        std::cout << "RenderEngine::removeOverridenParameter error: " <<
                     "Overriden parameter index is less than the smallest parameter index." <<
                     std::endl;
        return false;
    }

    auto iterator = std::find_if (overridenParameters.begin(),
                                  overridenParameters.end(),
                                  [&index] (const std::pair<int, float>& parameter)
                                  {
                                      return parameter.first == index;
                                  });

    bool exists = (iterator != overridenParameters.end());

    if (exists)
    {
        overridenParameters.erase(iterator);
        return true;
    }

    std::cout << "RenderEngine::removeOverridenParameter error: " <<
                 "Overriden parameter does not exist." <<
                 std::endl;
    return false;
}

//==============================================================================
void RenderEngine::fillAvailablePluginParameters (PluginPatch& params)
{
    params.clear();
    params.reserve (plugin->getNumParameters());

    int usedParameterAmount = 0;
    for (int i = 0; i < plugin->getNumParameters(); ++i)
    {
        // Ensure the parameter is not unused.
        if (plugin->getParameterName(i) != "Param")
        {
            ++usedParameterAmount;
            params.push_back (std::make_pair (i, 0.0f));
        }
    }
    params.shrink_to_fit();
}

//==============================================================================
const String RenderEngine::getPluginParametersDescription()
{
    String parameterListString ("");

    if (plugin != nullptr)
    {
        const OwnedArray<AudioProcessorParameter>& params = plugin->getParameters();
        for (int i = 0; i < params.size(); ++i)
        {
            const String index      = std::to_string(params[i]->getParameterIndex());
            const String name       = params[i]->getName(100);
//            const String label      = params[i]->getLabel();
//            const String defaultVal = std::to_string(params[i]->getDefaultValue());
//            const String nSteps     = std::to_string(params[i]->getNumSteps());
//            const String isDiscrete = std::to_string(params[i]->isDiscrete());
//            const String isBool     = std::to_string(params[i]->isBoolean());
//            const String s = typeid(params[i]).name();
//            const String valStrings = params[i]->getAllValueStrings().joinIntoString("\n");
//
//            std::cout << "\n=\ns = \t" << s << "\nvalStrings = \t" << valStrings << std::endl;
            

            parameterListString += index + ", " + name + "\n";
        }
    }
    else
    {
        std::cout << "Please load the plugin first!" << std::endl;
    }

    return parameterListString;
}

//void checkType(const OwnedArray<AudioProcessorParameter>& params)
//{
//
//}

//==============================================================================
const String RenderEngine::getProgramName()
{
    return plugin->getProgramName(0);
}

//==============================================================================
void RenderEngine::setPatch (const PluginPatch patch)
{
    const size_t currentParameterSize = pluginParameters.size();
    const size_t newPatchParameterSize = patch.size();

    if (currentParameterSize == newPatchParameterSize)
    {
        pluginParameters = patch;
    }
    else
    {
        std::cout << "RenderEngine::setPatch error: Incorrect patch size!" <<
        "\n- Current size:  " << currentParameterSize <<
        "\n- Supplied size: " << newPatchParameterSize << std::endl;
    }
}

//==============================================================================
float RenderEngine::getParameter (const int parameter)
{
    return plugin->getParameter (parameter);
}

//==============================================================================
void RenderEngine::setParameter (const int parameter, const float value)
{
    plugin->setParameter (parameter, value);
}

//==============================================================================
const PluginPatch RenderEngine::getPatch()
{
    if (overridenParameters.size() == 0)
        return pluginParameters;

    PluginPatch overridenPluginParameters = pluginParameters;
    std::pair<int, float> copy;

    for (auto& parameter : overridenPluginParameters)
    {
        // Should we have overriden this parameter's index...
        if (std::any_of(overridenParameters.begin(), overridenParameters.end(),
                        [parameter, &copy] (std::pair<int, float> p)
                        {
                            copy = p;
                            return p.first == parameter.first;
                        }))
        {
            parameter = copy;
        }
    }
    return overridenPluginParameters;
}

//==============================================================================
const size_t RenderEngine::getPluginParameterSize()
{
    return pluginParameters.size();
}

//==============================================================================
const std::vector<double> RenderEngine::getAudioFrames()
{
    return processedMonoAudioPreview;
}

//==============================================================================
const std::vector<double> RenderEngine::getRMSFrames()
{
    return rmsFrames;
}

//==============================================================================
bool RenderEngine::writeToWav(const std::string& path)
{
    const auto size = processedMonoAudioPreview.size();
    if (size == 0)
        return false;

    maxiRecorder recorder;
    recorder.setup (path);
    recorder.startRecording();
    const double* data = processedMonoAudioPreview.data();
    recorder.passData (data, size);
    recorder.stopRecording();
    recorder.saveToWav();
    return true;
}


//==============================================================================
void RenderEngine::loadPluginState(const std::string& inputPath)
{
    
}


//==============================================================================
void RenderEngine::savePluginState(const std::string &outputPath)
{
    File outfile = File(outputPath);
    FileOutputStream outstream(outfile);
    juce::MemoryBlock stateData = juce::MemoryBlock();
    plugin->getStateInformation(stateData);
    
    
}

//==============================================================================
const String RenderEngine::getPluginName()
{
    return pluginDescription.name;
}

//==============================================================================
const String RenderEngine::getPluginDescriptiveName()
{
    return pluginDescription.descriptiveName;
}
