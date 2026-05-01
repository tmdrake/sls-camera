namespace Microsoft.Samples.Kinect.KinectExplorer
{
    using System;
    using System.Collections.Generic;
    using System.Diagnostics.CodeAnalysis;
    using System.Timers;
    using System.Windows;
    using System.Windows.Controls;
    using System.Windows.Data;
    using System.Windows.Input;
    using Microsoft.Kinect;
    using Microsoft.Samples.Kinect.WpfViewers;

    public partial class KinectWindow : Window
    {
        public static readonly DependencyProperty KinectSensorProperty =
            DependencyProperty.Register(
                "KinectSensor",
                typeof(KinectSensor),
                typeof(KinectWindow),
                new PropertyMetadata(null));

        private readonly KinectWindowViewModel viewModel;

        /// <summary>
        /// Initializes a new instance of the KinectWindow class, which provides access to many KinectSensor settings
        /// and output visualization.
        /// </summary>
        private readonly List<string> ovilusWords = new List<string> { "SPIRIT", "GHOST", "SHADOW", "CHILD", "WOMAN", "MAN", "DEMON", "ANGEL", "LEAVE", "STAY", "HELP", "HERE", "COLD", "ENERGY", "YES", "NO", "DARK", "LIGHT", "FOLLOW", "GO" };
        private readonly Timer ovilusTimer;
        private readonly Random random = new Random();

        public KinectWindow()
        {
            this.viewModel = new KinectWindowViewModel();
            this.viewModel.KinectSensorManager = new KinectSensorManager();

            Binding sensorBinding = new Binding("KinectSensor");
            sensorBinding.Source = this;
            BindingOperations.SetBinding(this.viewModel.KinectSensorManager, KinectSensorManager.KinectSensorProperty, sensorBinding);

            this.viewModel.KinectSensorManager.SkeletonStreamEnabled = true;

            this.DataContext = this.viewModel;
            InitializeComponent();

            this.ovilusTimer = new Timer(8000);
            this.ovilusTimer.Elapsed += (s, e) => this.Dispatcher.Invoke(Ovilus_GenerateInternal);
            this.ovilusTimer.Start();
        }

        public KinectSensor KinectSensor
        {
            get { return (KinectSensor)GetValue(KinectSensorProperty); }
            set { SetValue(KinectSensorProperty, value); }
        }

        public void StatusChanged(KinectStatus status)
        {
            this.viewModel.KinectSensorManager.KinectSensorStatus = status;
        }

        private void Swap_Executed(object sender, ExecutedRoutedEventArgs e)
        {
            Grid colorFrom = null;
            Grid depthFrom = null;

            if (this.MainViewerHost.Children.Contains(this.ColorVis))
            {
                colorFrom = this.MainViewerHost;
                depthFrom = this.SideViewerHost;
            }
            else
            {
                colorFrom = this.SideViewerHost;
                depthFrom = this.MainViewerHost;
            }

            colorFrom.Children.Remove(this.ColorVis);
            depthFrom.Children.Remove(this.DepthVis);
            colorFrom.Children.Insert(0, this.DepthVis);
            depthFrom.Children.Insert(0, this.ColorVis);
        }

        private void Ovilus_Generate(object sender, RoutedEventArgs e)
        {
            Ovilus_GenerateInternal();
        }

        private void Ovilus_GenerateInternal()
        {
            string word = this.ovilusWords[this.random.Next(this.ovilusWords.Count)];
            this.OvilusWord.Text = word;
            this.OvilusHistory.Items.Insert(0, DateTime.Now.ToString("HH:mm:ss") + " - " + word);
            if (this.OvilusHistory.Items.Count > 12) this.OvilusHistory.Items.RemoveAt(this.OvilusHistory.Items.Count - 1);
        }
    }

    public class KinectWindowViewModel : DependencyObject
    {
        public static readonly DependencyProperty KinectSensorManagerProperty =
            DependencyProperty.Register(
                "KinectSensorManager",
                typeof(KinectSensorManager),
                typeof(KinectWindowViewModel),
                new PropertyMetadata(null));

        public static readonly DependencyProperty DepthTreatmentProperty =
            DependencyProperty.Register(
                "DepthTreatment",
                typeof(KinectDepthTreatment),
                typeof(KinectWindowViewModel),
                new PropertyMetadata(KinectDepthTreatment.ClampUnreliableDepths));

        public KinectSensorManager KinectSensorManager
        {
            get { return (KinectSensorManager)GetValue(KinectSensorManagerProperty); }
            set { SetValue(KinectSensorManagerProperty, value); }
        }

        public KinectDepthTreatment DepthTreatment
        {
            get { return (KinectDepthTreatment)GetValue(DepthTreatmentProperty); }
            set { SetValue(DepthTreatmentProperty, value); }
        }
    }

    /// <summary>
    /// The Command to swap the viewer in the main panel with the viewer in the side panel.
    /// </summary>
    public class KinectWindowsViewerSwapCommand : RoutedCommand
    {  
    }
}
